import re

SLOTS=["education_level","age_band","current_occupation","family_occupation","skills","interests","tools","mobility_level","max_travel_distance","employment_preference","time_available","district","block","constraints","training_duration_preference"]
QUESTIONS={
"en":{"education_level":"What is the highest level of education you completed? You can say skip.","age_band":"Which age group are you in? For example, 18 to 24. You can skip.","current_occupation":"What work do you do now? You can skip.","family_occupation":"What kind of work does your family do? You can skip.","skills":"What skills or work experience do you already have? You can skip.","interests":"What kind of work would you like to learn? You can skip.","tools":"Do you already have any tools, land, or workspace? You can skip.","mobility_level":"Can you travel for training, or do you need nearby support? You can skip.","max_travel_distance":"How far could you travel for training, in kilometres? You can skip.","employment_preference":"Would you prefer a wage job, self-employment, or either? You can skip.","time_available":"How much time can you give to training each week? You can skip.","district":"Which district are you in? You can skip.","block":"Which block or town are you in? You can skip.","constraints":"Is there anything that could make training difficult? You can skip.","training_duration_preference":"What training length would work for you? You can skip.","confirm":"Does this summary look right? Say yes to see pathways or no to review it."},
"hi":{"education_level":"आपने कितनी पढ़ाई पूरी की है? आप छोड़ सकते हैं।","age_band":"आपकी उम्र किस समूह में है? जैसे 18 से 24। आप छोड़ सकते हैं।","current_occupation":"आप अभी कौन सा काम करते हैं? आप छोड़ सकते हैं।","family_occupation":"आपके परिवार में कौन सा काम होता है? आप छोड़ सकते हैं।","skills":"आपको कौन से काम या हुनर आते हैं? आप छोड़ सकते हैं।","interests":"आप कौन सा काम सीखना चाहेंगे? आप छोड़ सकते हैं।","tools":"क्या आपके पास औज़ार, ज़मीन या काम की जगह है? आप छोड़ सकते हैं।","mobility_level":"क्या आप प्रशिक्षण के लिए यात्रा कर सकते हैं? आप छोड़ सकते हैं।","max_travel_distance":"आप प्रशिक्षण के लिए कितनी दूर जा सकते हैं? आप छोड़ सकते हैं।","employment_preference":"आप नौकरी चाहेंगे, अपना काम या दोनों? आप छोड़ सकते हैं।","time_available":"आप हर हफ्ते प्रशिक्षण के लिए कितना समय दे सकते हैं? आप छोड़ सकते हैं।","district":"आपका जिला कौन सा है? आप छोड़ सकते हैं।","block":"आपका ब्लॉक या शहर कौन सा है? आप छोड़ सकते हैं।","constraints":"क्या कोई बात प्रशिक्षण में कठिनाई कर सकती है? आप छोड़ सकते हैं।","training_duration_preference":"आपके लिए कितने समय का प्रशिक्षण ठीक रहेगा? आप छोड़ सकते हैं।","confirm":"क्या यह जानकारी सही है? विकल्प देखने के लिए हाँ कहें, बदलने के लिए नहीं कहें।"}}
SKIP={"skip","pass","not sure","छोड़ें","छोड़ो","पता नहीं","नहीं बताना"}

def first_slot(profile): return next((s for s in SLOTS if s not in profile and s not in profile.get("skipped_slots",[])),"confirm")
def question(slot,language): return QUESTIONS.get(language,QUESTIONS["en"]).get(slot,QUESTIONS["en"].get(slot,"Tell me a little more. You can say skip."))

def normalize(slot,text):
    t=text.strip(); low=t.lower()
    if low in SKIP:return None
    if slot=="education_level":
        if any(w in low for w in ["graduate","bachelor","degree","स्नातक"]):return "graduate"
        if any(w in low for w in ["12th","12वीं","बारहवीं"]):return "12th"
        if any(w in low for w in ["10th","10वीं","दसवीं"]):return "10th"
        if any(w in low for w in ["no formal","none","पढ़ाई नहीं"]):return "no_formal_schooling"
    if slot=="age_band":
        m=re.search(r"\b(\d{2})\b",low)
        if m:
            n=int(m.group(1));return "18-24" if n<25 else "25-34" if n<35 else "35-44" if n<45 else "45+"
        for phrase,value in [("18 to 24","18-24"),("25 to 34","25-34"),("35 to 44","35-44")]:
            if phrase in low:return value
    if slot=="max_travel_distance":
        m=re.search(r"\d+(?:\.\d+)?",low)
        if m:return float(m.group())
    if slot=="employment_preference":
        if any(w in low for w in ["self","own","business","अपना","स्वरोजगार"]):return "self_employment"
        if any(w in low for w in ["wage","job","salary","नौकरी"]):return "wage_employment"
        if any(w in low for w in ["either","both","दोनों"]):return "either"
    if slot=="district":
        if low in {"नागपुर","nagpur"}:return "Nagpur"
        if low in {"पुणे","pune"}:return "Pune"
    if slot in {"skills","interests","tools","constraints"}:
        return [x.strip() for x in re.split(r",| and | तथा | और |\n",t) if x.strip()]
    return t


YES_WORDS={"yes","y","yeah","yep","ok","okay","correct","right","हाँ","हां","हो","सही","ठीक"}
def is_yes(text):
    t=re.sub(r"[.,!?;:।\"'()\-]","",(text or "").lower()).strip()
    return t in YES_WORDS or t.startswith("yes ") or t.startswith("हाँ ") or t.startswith("हां ")

def transition(session,text):
    profile=dict(session.profile or {})
    if session.state=="CONSENT":
        if text.strip().lower() not in {"yes","y","हाँ","हां","हो","agree","i agree"}:
            return "CONSENT",profile,"Please choose yes to consent, or leave the assessment. / सहमति के लिए हाँ कहें।"
        return "INTERVIEW",profile,question(first_slot(profile),session.language)
    if session.state=="PROFILE_REVIEW":
        if is_yes(text):
            return "RECOMMENDATION",profile,("Your profile is ready. I’ll show pathways from the demo catalogue." if session.language=="en" else "आपकी जानकारी तैयार है। अब नमूना आजीविका विकल्प दिखाता हूँ।")
        return "PROFILE_REVIEW",profile,("You can correct or remove details in your profile below, then confirm when it looks right." if session.language=="en" else "नीचे अपनी जानकारी सुधारें या हटाएँ, फिर सही होने पर पुष्टि करें।")
    slot=first_slot(profile)
    if slot=="confirm":
        summary=", ".join(f"{k.replace('_',' ')}: {v}" for k,v in profile.items())
        return "PROFILE_REVIEW",profile,(f"I heard: {summary}. Is this right? Say yes or no." if session.language=="en" else f"मैंने सुना: {summary}. क्या यह सही है? हाँ या नहीं कहें।")
    value=normalize(slot,text)
    if value is not None:profile[slot]=value
    else:profile["skipped_slots"]=list(dict.fromkeys([*profile.get("skipped_slots",[]),slot]))
    next_=first_slot(profile)
    if next_=="confirm":
        summary=", ".join(f"{k.replace('_',' ')}: {v}" for k,v in profile.items())
        return "PROFILE_REVIEW",profile,(f"I heard: {summary}. Is this right? Say yes or no." if session.language=="en" else f"मैंने सुना: {summary}. क्या यह सही है? हाँ या नहीं कहें।")
    return "INTERVIEW",profile,question(next_,session.language)