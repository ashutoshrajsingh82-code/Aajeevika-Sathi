from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.db import Base
from app.knowledge.schemas import IngestDocument
from app.knowledge.service import KnowledgeService,INFO_UNAVAILABLE,chunk_text
from app.knowledge.embeddings import LocalHashEmbedding
from app.models import Pathway,TrainingCentre,DemandSignal,KnowledgeChunk
from app.knowledge.extractors import ExtractedPage,extract_document
from app.knowledge.citations import LexicalEntailmentChecker
from app.knowledge.retrievers import HashRetriever,HybridRetriever,QueryClassifier
from app.knowledge.evaluation import retrieval_metrics,claim_metrics
import json
from pathlib import Path

def database():
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return engine

def doc(*,status="VERIFIED",category="scheme",district="Nagpur",text=None,**kwargs):
    return IngestDocument(title="Sample scheme reference",source="https://socialjustice.gov.in/schemes/104",authority="Example Department",category=category,district=district,state="Maharashtra",status=status,
        last_verified="2026-09-30",content=text or ("Applicants must submit the form at the district office. The office verifies eligibility before enrolment. "*12),**kwargs)

def test_chunking_overlaps_and_respects_limits():
    source="word "*500
    chunks=chunk_text(source,size=100,overlap=20)
    assert len(chunks)>1
    assert all(len(chunk)<=100 for chunk in chunks)
    assert chunks[0][-20:].strip() in chunks[1]
    assert chunk_text("  ")==[]

def test_local_embedding_is_deterministic_and_semantic_features_overlap():
    embedder=LocalHashEmbedding()
    first=embedder.embed("skill training computer")
    assert first==embedder.embed("skill training computer")
    assert sum(a*b for a,b in zip(first,embedder.embed("computer skill training")))>0

def test_ingestion_metadata_retrieval_and_category_district_filter():
    engine=database();service=KnowledgeService()
    with Session(engine) as db:
        created,count=service.ingest(db,doc(status="DEMO"))
        service.ingest(db,doc(category="course",district="Pune",text="Advanced tailoring course at a sample centre."))
        db.commit()
        assert count>1
        hits=service.search_schemes(db,"Who verifies eligibility for the scheme?",district="Nagpur")
        assert hits and hits[0]["document"]["authority"]=="Example Department"
        assert hits[0]["document"]["status"]=="DEMO"
        assert hits[0]["document"]["last_verified"]=="2026-09-30"
        assert all(hit["document"]["category"]=="scheme" for hit in hits)
        assert created.id==hits[0]["document"]["document_id"]

def test_demo_and_stale_sources_are_explicit_and_require_verification():
    engine=database();service=KnowledgeService()
    with Session(engine) as db:
        service.ingest(db,doc(status="DEMO",category="training_centre",text="Sample training centre offers sample sewing sessions."))
        service.ingest(db,doc(status="STALE",category="scheme",district="Pune",text="Older scheme guide says check the office for eligibility."))
        db.commit()
        demo=service.answer(db,"Where is a sample sewing centre?",category="training_centre")
        stale=service.answer(db,"How do I verify eligibility?",category="scheme",district="Pune")
        assert demo["answer"].startswith("DEMO DATA —")
        assert demo["status"]=="DEMO" and demo["requires_counsellor_verification"]
        assert stale["status"]=="STALE" and "Requires counsellor verification" in stale["answer"]

def test_existing_pathways_and_centres_are_exposed_only_as_demo_data():
    engine=database();service=KnowledgeService()
    with Session(engine) as db:
        db.add(Pathway(id="demo-course",title="Sample computer course",sector="Digital",description="Basic computer skills sample.",skills=["basic computer"],prerequisites=[],min_education="verify",duration_hours=None,self_employment=False,source="SIMULATED DEMO PATHWAY",source_url="",active=True))
        db.add(TrainingCentre(id="demo-centre",name="Sample Centre",district="Nagpur",block="Sample block",latitude=0,longitude=0,address="Sample address",contact="NOT VERIFIED",accessibility="NOT VERIFIED",source="SIMULATED SAMPLE",pathway_ids=[]))
        db.commit()
        course=service.search_courses(db,"computer course",district="Nagpur")
        centre=service.search_training_centres(db,"sample training centre",district="Nagpur")
        assert course and course[0]["document"]["status"]=="DEMO"
        assert course[0]["text"].startswith("DEMO DATA —")
        assert centre and centre[0]["document"]["status"]=="DEMO"
        assert "Sample centre record only" in centre[0]["text"]

def test_unknown_and_hallucination_attempt_fail_closed():
    engine=database();service=KnowledgeService()
    class ExplodingClient:
        def generate_json(self,*args,**kwargs):raise AssertionError("No model call without retrieved evidence")
    with Session(engine) as db:
        unknown=service.answer(db,"Which scheme pays exactly 50000 rupees?",ExplodingClient())
        assert unknown["answer"]==INFO_UNAVAILABLE and unknown["status"]=="UNKNOWN"
        assert unknown["sources"]==[] and unknown["ai_used"] is False

def test_model_must_cite_retrieved_chunk_and_demo_notice_is_preserved():
    engine=database();service=KnowledgeService()
    class InvalidCitationClient:
        def generate_json(self,*args,**kwargs):
            from app.knowledge.schemas import GroundedAnswer
            return GroundedAnswer(answer="The scheme gives guaranteed money.",cited_chunk_ids=["not-retrieved"])
    with Session(engine) as db:
        service.ingest(db,doc(status="DEMO",text="Synthetic sample scheme detail for testing."));db.commit()
        answer=service.answer(db,"What is this sample scheme?",InvalidCitationClient())
        assert answer["ai_used"] is False
        assert answer["answer"].startswith("DEMO DATA —")
        assert "guaranteed money" not in answer["answer"]

def test_identical_document_is_deduplicated_and_status_can_be_refreshed():
    engine=database();service=KnowledgeService()
    with Session(engine) as db:
        original,_=service.ingest(db,doc(status="STALE"));db.commit()
        refreshed,count=service.ingest(db,doc(status="VERIFIED"));db.commit()
        assert refreshed.id==original.id and count==0 and refreshed.status=="STALE"

def test_knowledge_api_requires_manual_official_verification_and_returns_sources(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app,admin_required
    from app.db import get_db
    engine=database()
    def db_dependency():
        with Session(engine) as db:yield db
    from app.knowledge import sources
    content=b"A counsellor verifies eligibility at the district office."
    app.dependency_overrides[get_db]=db_dependency
    try:
        with TestClient(app) as client:
            assert client.post("/api/v1/admin/knowledge/documents/upload").status_code==401
            app.dependency_overrides[admin_required]=lambda:{"role":"admin","username":"test"}
            response=client.post("/api/v1/admin/knowledge/documents/upload",files={"file":("eligibility.txt",content,"text/plain")},data={"metadata":'{"title":"Eligibility process","source":"https://socialjustice.gov.in/schemes/104","source_url":"https://socialjustice.gov.in/schemes/104","authority":"Example Department","category":"eligibility","district":"Nagpur","state":"Maharashtra","source_type":"official_government","status":"UNKNOWN"}'})
            ingested=response
            assert ingested.status_code==200
            document_id=ingested.json()["document_id"]
            monkeypatch.setattr(sources,"download_official",lambda url:(content,"text/plain"))
            verified=client.post(f"/api/v1/admin/knowledge/documents/{document_id}/verify",json={"decision":"OFFICIAL_VERIFIED","note":"Reviewed official source and extracted text."})
            assert verified.status_code==200
            result=client.post("/api/v1/knowledge/ask",json={"question":"How is eligibility verified?","category":"eligibility","district":"Nagpur"})
            assert result.status_code==200
            body=result.json()
            assert body["status"]=="OFFICIAL_VERIFIED"
            assert body["sources"][0]["authority"]=="Example Department"
            assert "eligibility" in body["answer"].lower()
    finally:
        app.dependency_overrides.pop(admin_required,None)
        app.dependency_overrides.pop(get_db,None)

def test_claim_level_checker_accepts_direct_evidence_and_rejects_unsupported_amounts():
    checker=LexicalEntailmentChecker()
    evidence="The simulated programme provides monetary assistance of 200 training tokens."
    assert checker.verify("The simulated programme provides monetary assistance of 200 training tokens.",evidence)["entailment_status"]=="SUPPORTED"
    rejected=checker.verify("The simulated programme provides 50,000 rupees.",evidence)
    assert rejected["entailment_status"]=="UNSUPPORTED"

def test_supported_model_claim_is_page_cited_and_unsupported_claim_is_removed():
    from app.knowledge.schemas import GroundedAnswer
    engine=database();service=KnowledgeService()
    with Session(engine) as db:
        document=doc(status="DEMO",text="DEMO DATA: Simulated Alpha provides 200 training tokens to participants.")
        document=document.model_copy(update={"scheme_name":"Synthetic Alpha"})
        stored,_=service.ingest(db,document,pages=[ExtractedPage(4,"Benefits","DEMO DATA: Simulated Alpha provides 200 training tokens to participants.")])
        db.commit();hits=service.search_documents(db,"How many training tokens does Alpha provide?",category="scheme")
        cite=hits[0]["chunk_id"]
        class Client:
            def __init__(self,claims):self.claims=claims
            def generate_json(self,*args,**kwargs):return GroundedAnswer(answer="unsupported prose must be ignored",claims=self.claims,cited_chunk_ids=[cite])
        accepted=service.answer(db,"How many training tokens does Alpha provide?",Client([{"text":"DEMO DATA: Simulated Alpha provides 200 training tokens to participants.","cited_chunk_ids":[cite]}]),category="scheme")
        assert accepted["claims"][0]["page_number"]==4
        assert "Page 4" in accepted["answer"]
        unsupported=service.answer(db,"How many training tokens does Alpha provide?",Client([{"text":"Alpha pays 50000 rupees to all users.","cited_chunk_ids":[cite]}]),category="scheme")
        assert "50000 rupees" not in unsupported["answer"]
        assert "200 training tokens" in unsupported["answer"]

def test_invalid_claim_citation_is_rejected_and_source_fallback_is_extractively_grounded():
    from app.knowledge.schemas import GroundedAnswer
    engine=database();service=KnowledgeService()
    with Session(engine) as db:
        service.ingest(db,doc(status="DEMO",text="DEMO DATA: Sample Beta offers weekend sewing lessons."));db.commit()
        class Client:
            def generate_json(self,*args,**kwargs):return GroundedAnswer(answer="Beta pays everyone 50000 rupees.",claims=[{"text":"Beta pays everyone 50000 rupees.","cited_chunk_ids":["unrelated-id"]}],cited_chunk_ids=["unrelated-id"])
        result=service.answer(db,"What are the sample Beta lessons?",Client(),category="scheme")
        assert "50000 rupees" not in result["answer"]
        assert result["status"]=="DEMO"

def test_verified_documents_are_retrieved_hybridly_for_paraphrase_and_filtered_by_metadata():
    engine=database();service=KnowledgeService()
    with Session(engine) as db:
        service.ingest(db,doc(status="DEMO",text="DEMO DATA: Simulated programme Alpha provides monetary assistance of 200 training tokens to enrolled participants."));db.commit()
        exact=service.search_schemes(db,"What monetary assistance does Alpha provide?")
        paraphrase=service.search_schemes(db,"How much financial help can enrolled participants receive?")
        assert exact and exact[0]["document"]["status"]=="DEMO"
        assert paraphrase and "Alpha" in paraphrase[0]["text"]
        assert QueryClassifier.classify("What financial assistance is available?")["intent"]=="BENEFITS"

def test_extraction_preserves_txt_pages_html_headings_and_tables():
    pages,status=extract_document(b"Heading\nPage-boundary text.","guideline.txt")
    assert status=="text" and pages[0].page_number==1 and "Heading" in pages[0].text
    html=b"<h1>Eligibility</h1><table><tr><th>Requirement</th><th>Value</th></tr><tr><td>Age</td><td>18 years</td></tr></table>"
    pages,status=extract_document(html,"source.html")
    assert status=="html" and "Eligibility" in pages[0].text and "Requirement | Value" in pages[0].text

def test_pdf_pages_docx_headings_tables_and_scanned_detection():
    import fitz
    from docx import Document
    from io import BytesIO
    pdf=fitz.open()
    for line in ("Page one eligibility details.","Page two application steps."):
        page=pdf.new_page();page.insert_text((72,72),line)
    pdf_bytes=pdf.tobytes();pages,status=extract_document(pdf_bytes,"guidelines.pdf",ocr_enabled=False)
    assert status=="pdf_text" and [page.page_number for page in pages]==[1,2]
    assert "Page two" in pages[1].text
    scan=fitz.open();scan.new_page();scanned_pages,scan_status=extract_document(scan.tobytes(),"scan.pdf",ocr_enabled=False)
    assert scan_status=="ocr_required" and scanned_pages[0].page_number==1
    word=Document();word.add_heading("Eligibility",level=1);word.add_paragraph("Review is required.");table=word.add_table(rows=1,cols=2);table.rows[0].cells[0].text="Field";table.rows[0].cells[1].text="Value";stream=BytesIO();word.save(stream)
    docx_pages,docx_status=extract_document(stream.getvalue(),"guidelines.docx")
    assert docx_status=="docx" and docx_pages[0].page_number is None
    assert docx_pages[0].section=="Eligibility" and "Field | Value" in docx_pages[0].text

def test_official_verification_requires_allowlist_and_exact_current_source_bytes(monkeypatch):
    from app.knowledge import sources
    engine=database();service=KnowledgeService()
    with Session(engine) as db:
        content=b"Officially imported source text."
        blocked=IngestDocument(title="lookalike",source="https://example.gov.in/document.pdf",source_url="https://example.gov.in/document.pdf",authority="Government-like label",category="scheme",source_type="official_government",content=content.decode())
        blocked_doc,_=service.ingest(db,blocked,original_content=content,filename="source.txt")
        monkeypatch.setattr(sources,"download_official",lambda url:(content,"text/plain"))
        try:service.verify_document(db,blocked_doc.id,"OFFICIAL_VERIFIED","I reviewed this government source carefully.","admin");assert False
        except ValueError as error:assert "configured official" in str(error)
        allowed=blocked.model_copy(update={"title":"Official source","source":"https://socialjustice.gov.in/schemes/104","source_url":"https://socialjustice.gov.in/schemes/104"})
        allowed_doc,_=service.ingest(db,allowed,original_content=content,filename="source.txt")
        monkeypatch.setattr(sources,"download_official",lambda url:(b"Different live source content.","text/plain"))
        try:service.verify_document(db,allowed_doc.id,"OFFICIAL_VERIFIED","I reviewed this government source carefully.","admin");assert False
        except ValueError as error:assert "changed since ingestion" in str(error)

def test_query_classifier_does_not_assert_facts_and_metrics_are_reported():
    assert QueryClassifier.classify("What exact subsidy can I receive?")=={"intent":"BENEFITS","category":"scheme"}
    assert QueryClassifier.classify("unknown question") == {"intent":"GENERAL","category":None}
    assert claim_metrics([])["citation_coverage"]==1.0
    metrics=retrieval_metrics([{"query":"not present","relevant_document_ids":[],"answerable":False}],lambda *args:[],top_k=3)
    assert metrics["abstention_accuracy"]==1.0 and metrics["abstention_count"]==1

def test_synthetic_benchmark_measures_hash_vs_hybrid_retrieval():
    benchmark=json.loads((Path(__file__).parents[1]/"app"/"knowledge"/"evaluation_cases.json").read_text(encoding="utf-8"))
    engine=database();embedder=LocalHashEmbedding();service=KnowledgeService(embedder=embedder)
    with Session(engine) as db:
        for fixture in benchmark["documents"]:
            category="course" if "Beta" in fixture["title"] else "scheme"
            item=IngestDocument(title=fixture["title"],source="synthetic benchmark fixture",authority="Synthetic test fixture",category=category,status="DEMO",source_type="demo",content=fixture["text"])
            document,_=service.ingest(db,item);old_id=document.id;document.id=fixture["id"]
            db.query(KnowledgeChunk).filter_by(document_id=old_id).update({"document_id":fixture["id"]})
        db.commit()
        cases=benchmark["questions"]
        hash_metrics=retrieval_metrics(cases,lambda q,k,f:HashRetriever(embedder).retrieve(db,q,k,f),top_k=1)
        hybrid_metrics=retrieval_metrics(cases,lambda q,k,f:HybridRetriever(HashRetriever(embedder),embedder).retrieve(db,q,k,f),top_k=1)
        assert hash_metrics["count"]==5 and hybrid_metrics["count"]==5
        assert 0<=hybrid_metrics["recall_at_k"]<=1
        assert 0<=hybrid_metrics["precision_at_k"]<=1
        assert 0<=hybrid_metrics["mrr"]<=1
        assert 0<=hybrid_metrics["ndcg_at_k"]<=1
        assert 0<=hybrid_metrics["abstention_accuracy"]<=1

def _image_pdf(*,mixed=False):
    import fitz
    from PIL import Image,ImageDraw
    from io import BytesIO
    image=Image.new("RGB",(900,400),"white");ImageDraw.Draw(image).text((40,80),"Scanned eligibility document",fill="black")
    stream=BytesIO();image.save(stream,format="PNG")
    document=fitz.open()
    if mixed:
        page=document.new_page();page.insert_text((50,60),"Native text page with application details and instructions.")
    page=document.new_page();page.insert_image(page.rect,stream=stream.getvalue())
    return document.tobytes()

def test_image_only_scanned_pdf_reports_missing_tesseract_without_losing_original(monkeypatch):
    import app.knowledge.extractors as extractors
    monkeypatch.setattr(extractors,"_ocr_runtime",lambda:(None,None,None,"ocr_required"))
    pages,status=extract_document(_image_pdf(),"scan.pdf")
    assert status=="ocr_required" and pages[0].text==""
    assert extractors.ocr_status_message(status).startswith("Scanned document requires OCR, but no OCR engine is configured.")

def test_mixed_pdf_keeps_native_text_and_flags_pages_requiring_ocr(monkeypatch):
    import app.knowledge.extractors as extractors
    monkeypatch.setattr(extractors,"_ocr_runtime",lambda:(None,None,None,"ocr_required"))
    pages,status=extract_document(_image_pdf(mixed=True),"mixed.pdf")
    assert status=="pdf_partial_text_ocr_required"
    assert "Native text page" in pages[0].text and pages[1].text==""

def test_tesseract_failure_and_low_confidence_are_distinct_review_states(monkeypatch):
    import fitz
    import app.knowledge.extractors as extractors
    monkeypatch.setattr(extractors,"_ocr_runtime",lambda:((fitz,None,None),"eng+hin",None))
    monkeypatch.setattr(extractors,"_ocr_image",lambda image,filename,page_number,ocr_enabled:(ExtractedPage(page_number,None,""),"ocr_failed"))
    failed,status=extract_document(_image_pdf(),"scan.pdf")
    assert status=="ocr_failed" and failed[0].text==""
    monkeypatch.setattr(extractors,"_ocr_image",lambda image,filename,page_number,ocr_enabled:(ExtractedPage(page_number,"Eligibility","Eligibility is reviewed by an officer.",True,"tesseract","eng+hin",.31),None))
    low,status=extract_document(_image_pdf(),"scan.pdf")
    assert status=="pdf_ocr_low_confidence" and low[0].ocr_used and low[0].ocr_confidence==.31

def test_multilingual_ocr_language_configuration_and_missing_traineddata(monkeypatch):
    import sys
    from types import SimpleNamespace
    import app.knowledge.extractors as extractors
    monkeypatch.setenv("OCR_LANGUAGES","eng+hin")
    monkeypatch.setitem(sys.modules,"pytesseract",SimpleNamespace(get_tesseract_version=lambda:"5.0",get_languages=lambda config:["eng"]))
    runtime=extractors._ocr_runtime()
    assert runtime[3]=="ocr_language_unavailable"
    monkeypatch.setenv("OCR_LANGUAGES","eng+hin;cat")
    try:extractors._configured_languages();assert False
    except ValueError as error:assert "OCR_LANGUAGES" in str(error)

def test_ocr_upload_without_text_is_retained_unindexed_and_cannot_be_verified(monkeypatch):
    from app.knowledge import sources
    engine=database();service=KnowledgeService();original=b"retained-scanned-source-bytes"
    item=doc(status="UNKNOWN",source_type="official_government",text="No text extracted; OCR required.")
    with Session(engine) as db:
        stored,count=service.ingest(db,item,original_content=original,filename="scan.pdf",pages=[ExtractedPage(1,None,"")],extraction_status="ocr_required");db.commit()
        assert count==0 and stored.original_content==original and stored.extraction_message
        monkeypatch.setattr(sources,"download_official",lambda url:(original,"application/pdf"))
        try:service.verify_document(db,stored.id,"OFFICIAL_VERIFIED","Checked document and source metadata.","admin");assert False
        except ValueError as error:assert "requires OCR" in str(error)

def test_verified_ocr_requires_explicit_admin_confirmation_and_then_retrieves(monkeypatch):
    from app.knowledge import sources
    engine=database();service=KnowledgeService();original=b"verified-scan-original-bytes"
    item=doc(status="UNKNOWN",source_type="official_government",text="Eligibility is reviewed by the district officer.")
    page=ExtractedPage(12,"Eligibility","Eligibility is reviewed by the district officer.",True,"tesseract","eng+hin",.91)
    with Session(engine) as db:
        stored,count=service.ingest(db,item,original_content=original,filename="official.pdf",pages=[page],extraction_status="pdf_ocr_success")
        db.commit()
        assert count==1 and not service.search_schemes(db,"How is eligibility reviewed?")
        monkeypatch.setattr(sources,"download_official",lambda url:(original,"application/pdf"))
        try:service.verify_document(db,stored.id,"OFFICIAL_VERIFIED","Compared extracted page with original scan.","admin");assert False
        except ValueError as error:assert "explicit administrator confirmation" in str(error)
        verified=service.verify_document(db,stored.id,"OFFICIAL_VERIFIED","Compared extracted page with original scan.","admin",ocr_reviewed=True)
        db.commit()
        hits=service.search_schemes(db,"How is eligibility reviewed?")
        assert verified.ocr_reviewed and hits and hits[0]["document"]["verified"]
        assert hits[0]["ocr_used"] and hits[0]["ocr_confidence"]==.91 and hits[0]["page_number"]==12

def test_admin_upload_returns_actionable_ocr_required_state_and_rejects_approval(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app,admin_required
    from app.db import get_db
    import app.main as main
    engine=database()
    def db_dependency():
        with Session(engine) as db:yield db
    monkeypatch.setattr(main,"extract_document",lambda content,filename:([ExtractedPage(1,None,"")],"ocr_required"))
    app.dependency_overrides[get_db]=db_dependency
    app.dependency_overrides[admin_required]=lambda:{"role":"admin","username":"test"}
    try:
        with TestClient(app) as client:
            response=client.post("/api/v1/admin/knowledge/documents/upload",files={"file":("scan.pdf",b"original scan bytes","application/pdf")},data={"metadata":'{"title":"Scanned guideline","source":"https://socialjustice.gov.in/schemes/104","source_url":"https://socialjustice.gov.in/schemes/104","authority":"Example Department","category":"scheme","source_type":"official_government","status":"UNKNOWN","content":"pending OCR"}'})
            assert response.status_code==200
            body=response.json()
            assert body["extraction_status"]=="ocr_required" and body["ocr_available"] is False
            assert "no OCR engine" in body["extraction_message"] and body["chunk_count"]==0
            rejected=client.post(f"/api/v1/admin/knowledge/documents/{body['document_id']}/verify",json={"decision":"OFFICIAL_VERIFIED","note":"Reviewed this source for verification."})
            assert rejected.status_code==422 and "OCR" in rejected.json()["detail"]
    finally:
        app.dependency_overrides.pop(admin_required,None)
        app.dependency_overrides.pop(get_db,None)
