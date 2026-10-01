"""Page-aware text extraction with explicit, fail-safe multilingual OCR states."""
from dataclasses import dataclass
from html.parser import HTMLParser
from io import BytesIO
import os
import re

MAX_DOCUMENT_BYTES=20*1024*1024
DEFAULT_OCR_LANGUAGES="eng+hin"
DEFAULT_MIN_OCR_CONFIDENCE=60.0

@dataclass(frozen=True)
class ExtractedPage:
    page_number:int|None
    section:str|None
    text:str
    ocr_used:bool=False
    ocr_engine:str|None=None
    ocr_language:str|None=None
    ocr_confidence:float|None=None

class _HtmlText(HTMLParser):
    def __init__(self):super().__init__();self.skip=0;self.parts=[]
    def handle_starttag(self,tag,attrs):
        if tag in {"script","style","noscript","svg"}:self.skip+=1
        if tag in {"p","li","tr","h1","h2","h3","h4","br"}:self.parts.append("\n")
        if tag in {"td","th"}:self.parts.append(" | ")
    def handle_endtag(self,tag):
        if tag in {"script","style","noscript","svg"} and self.skip:self.skip-=1
        if tag in {"p","li","tr","h1","h2","h3","h4"}:self.parts.append("\n")
    def handle_data(self,data):
        if not self.skip:self.parts.append(data)

def clean_text(text:str)->str:
    text=text.replace("\x00","").replace("\u00ad","")
    text=re.sub(r"[ \t]+"," ",text)
    text=re.sub(r" *\n *","\n",text)
    text=re.sub(r"\n{3,}","\n\n",text)
    return text.strip()

def ocr_status_message(status:str,ocr_available:bool|None=None)->str:
    messages={
        "pdf_text":"Text extracted from the PDF.",
        "pdf_partial_text":"Some pages contain native text; other pages need OCR.",
        "pdf_partial_text_ocr_required":"Some pages contain native text; OCR is required for remaining pages.",
        "pdf_ocr_success":"OCR text extracted. Administrator verification is still required.",
        "pdf_ocr_low_confidence":"OCR confidence is low. Review the extracted pages against the original.",
        "ocr_required":"Scanned document requires OCR, but no OCR engine is configured. Install Tesseract, install configured language data, then re-index.",
        "ocr_language_unavailable":"A configured Tesseract language model is missing. Install the matching traineddata file, then re-index.",
        "ocr_failed":"OCR failed. No OCR text from the failed page was indexed; check the source image and Tesseract setup, then re-index.",
        "ocr_partial_failure":"OCR did not complete for every scanned page. Check the source and Tesseract setup, then re-index before verification.",
        "pdf_scanned_ocr_unavailable":"Scanned document requires OCR, but no OCR engine is configured. Install Tesseract, install configured language data, then re-index.",
        "pdf_text+ocr":"OCR text extracted. Administrator verification is still required.",
        "text":"Text extracted.","html":"Text extracted.","docx":"Text extracted.",
    }
    return messages.get(status,"Document is awaiting administrator verification.")

def extract_document(content:bytes,filename:str,*,ocr_enabled:bool=True)->tuple[list[ExtractedPage],str]:
    if not content:raise ValueError("Document is empty")
    if len(content)>MAX_DOCUMENT_BYTES:raise ValueError("Document exceeds the 20 MB ingestion limit")
    suffix=filename.lower().rsplit(".",1)[-1] if "." in filename else ""
    if suffix=="pdf" or content.startswith(b"%PDF"):
        return _extract_pdf(content,ocr_enabled)
    if suffix in {"png","jpg","jpeg","tif","tiff","bmp","webp"}:
        return _extract_image(content,filename,ocr_enabled)
    if suffix=="docx" or content.startswith(b"PK\x03\x04"):
        return _extract_docx(content)
    if suffix in {"txt","text"} or filename.lower().endswith(".md"):
        try:text=content.decode("utf-8-sig")
        except UnicodeDecodeError:text=content.decode("cp1252",errors="replace")
        return [ExtractedPage(1,None,clean_text(text))],"text"
    if suffix in {"html","htm"}:
        parser=_HtmlText();parser.feed(content.decode("utf-8",errors="replace"))
        return [ExtractedPage(1,None,clean_text("".join(parser.parts)))],"html"
    raise ValueError("Supported document types are PDF, DOCX, TXT, MD, HTML, and common image formats")

def _configured_languages()->str:
    languages=os.getenv("OCR_LANGUAGES",DEFAULT_OCR_LANGUAGES).strip()
    if not re.fullmatch(r"[A-Za-z0-9_+-]{2,100}",languages):raise ValueError("OCR_LANGUAGES must be a + separated Tesseract language list such as eng+hin")
    return languages

def _ocr_runtime():
    """Return the OCR modules and a precise setup error, without hiding missing language data."""
    try:
        try:import pymupdf as fitz
        except ImportError:import fitz
        import pytesseract
        from PIL import Image,ImageEnhance,ImageFilter,ImageOps
    except ImportError as exc:return None,None,None,"ocr_required"
    configured_executable=os.getenv("TESSERACT_CMD","").strip()
    if configured_executable:pytesseract.pytesseract.tesseract_cmd=configured_executable
    try:pytesseract.get_tesseract_version()
    except Exception:return None,None,None,"ocr_required"
    try:available=set(pytesseract.get_languages(config=""))
    except Exception:return None,None,None,"ocr_language_unavailable"
    languages=_configured_languages()
    missing=set(languages.split("+"))-available
    if missing:return None,None,None,"ocr_language_unavailable"
    return (fitz,pytesseract,(Image,ImageEnhance,ImageFilter,ImageOps)),languages,None

def _prepare_image(image_modules,image):
    Image,ImageEnhance,ImageFilter,ImageOps=image_modules
    # Work only on an in-memory OCR copy; the retained original bytes never change.
    image=ImageOps.grayscale(image)
    image.thumbnail((3500,3500),Image.Resampling.LANCZOS)
    image=ImageOps.autocontrast(image,cutoff=1)
    image=ImageEnhance.Contrast(image).enhance(1.35)
    image=image.filter(ImageFilter.MedianFilter(size=3))
    # Threshold only clearly bimodal pages; preserve grayscale for photographs/faint print.
    histogram=image.histogram();dark=sum(histogram[:90]);light=sum(histogram[166:])
    if dark+light and min(dark,light)/(dark+light)>.08:
        image=image.point(lambda value:255 if value>160 else 0)
    return image

def _ocr_image(image,filename:str,page_number:int|None,ocr_enabled:bool):
    if not ocr_enabled:return ExtractedPage(page_number,None,""),"ocr_required"
    runtime=_ocr_runtime()
    if runtime[0] is None:return ExtractedPage(page_number,None,""),runtime[3]
    fitz,pytesseract,image_modules=runtime[0]
    languages=runtime[1]
    try:
        prepared=_prepare_image(image_modules,image)
        data=pytesseract.image_to_data(prepared,lang=languages,output_type=pytesseract.Output.DICT,config="--psm 3")
        text=clean_text(pytesseract.image_to_string(prepared,lang=languages,config="--psm 3"))
        confidences=[]
        for raw in data.get("conf",[]):
            try:
                score=float(raw)
                if score>=0:confidences.append(score)
            except (TypeError,ValueError):continue
        confidence=sum(confidences)/len(confidences)/100 if confidences else 0.0
        result=ExtractedPage(page_number,_last_heading(text),text,True,"tesseract",languages,round(confidence,4))
        return result,None if text else "ocr_failed"
    except Exception:return ExtractedPage(page_number,None,""),"ocr_failed"

def _extract_image(content:bytes,filename:str,ocr_enabled:bool):
    try:from PIL import Image
    except ImportError:return [ExtractedPage(1,None,"")],"ocr_required"
    try:image=Image.open(BytesIO(content));image.load()
    except Exception as exc:raise ValueError("Image file is invalid or unsupported") from exc
    page,status=_ocr_image(image,filename,1,ocr_enabled)
    if status:return [page],status
    if not page.text:return [page],"ocr_failed"
    threshold=float(os.getenv("OCR_MIN_CONFIDENCE",str(DEFAULT_MIN_OCR_CONFIDENCE)))/100
    return [page],"pdf_ocr_low_confidence" if (page.ocr_confidence or 0)<threshold else "pdf_ocr_success"

def _extract_pdf(content:bytes,ocr_enabled:bool):
    try:from pypdf import PdfReader
    except ImportError as exc:raise RuntimeError("PDF support requires the pypdf package") from exc
    reader=PdfReader(BytesIO(content));pages=[];sparse=[];native_count=0
    for index,page in enumerate(reader.pages,1):
        try:text=page.extract_text(extraction_mode="layout") or ""
        except (TypeError,KeyError,ValueError):
            try:text=page.extract_text() or ""
            except (KeyError,ValueError):text=""
        text=clean_text(text)
        if len(text)<24:sparse.append(index)
        else:native_count+=1
        pages.append(ExtractedPage(index,_last_heading(text),text))
    if not sparse:return pages,"pdf_text"
    if not ocr_enabled:return pages,"pdf_partial_text" if native_count else "ocr_required"
    runtime=_ocr_runtime()
    if runtime[0] is None:return pages,"pdf_partial_text_ocr_required" if native_count else runtime[3]
    fitz=runtime[0][0];ocr_statuses=[];threshold=float(os.getenv("OCR_MIN_CONFIDENCE",str(DEFAULT_MIN_OCR_CONFIDENCE)))/100
    try:
        rendered=fitz.open(stream=content,filetype="pdf")
        dpi=max(120,min(400,int(os.getenv("OCR_DPI","250"))))
        scale=dpi/72
        for index in sparse:
            try:
                pixmap=rendered[index-1].get_pixmap(matrix=fitz.Matrix(scale,scale),alpha=False)
                from PIL import Image
                image=Image.open(BytesIO(pixmap.tobytes("png")));image.load()
                extracted,status=_ocr_image(image,"pdf",index,ocr_enabled)
            except Exception:extracted,status=ExtractedPage(index,None,""),"ocr_failed"
            ocr_statuses.append(status)
            if not status and extracted.text:pages[index-1]=extracted
        rendered.close()
    except Exception:return pages,"ocr_failed"
    if any(status in {"ocr_required","ocr_language_unavailable"} for status in ocr_statuses):
        return pages,"pdf_partial_text_ocr_required" if native_count else next(status for status in ocr_statuses if status in {"ocr_required","ocr_language_unavailable"})
    if any(status for status in ocr_statuses):return pages,"ocr_partial_failure" if native_count else "ocr_failed"
    confidences=[page.ocr_confidence for page in pages if page.ocr_used and page.ocr_confidence is not None]
    if any((page.ocr_confidence or 0)<threshold for page in pages if page.ocr_used):return pages,"pdf_ocr_low_confidence"
    return pages,"pdf_ocr_success"

def _extract_docx(content:bytes):
    try:from docx import Document
    except ImportError as exc:raise RuntimeError("DOCX support requires python-docx") from exc
    document=Document(BytesIO(content));section=None;groups={}
    for paragraph in document.paragraphs:
        text=clean_text(paragraph.text)
        if not text:continue
        style=(paragraph.style.name or "").lower()
        if style.startswith("heading"):section=text
        groups.setdefault(section,[]).append(text)
    for table in document.tables:
        for row in table.rows:
            cells=[clean_text(cell.text) for cell in row.cells]
            if any(cells):groups.setdefault(section,[]).append(" | ".join(cells))
    pages=[ExtractedPage(None,heading,"\n".join(values)) for heading,values in groups.items()]
    return pages or [ExtractedPage(None,None,"")],"docx"

def _last_heading(text:str)->str|None:
    for line in reversed(text.splitlines()):
        candidate=line.strip()
        if candidate and len(candidate)<=160 and (candidate.isupper() or candidate.startswith(("Chapter ","Section "))):return candidate
    return None
