import math
from .config import WEIGHTS
from .models import Pathway, TrainingCentre, DemandSignal

ALIASES={"दर्जी":"tailoring","सिलाई":"stitching","नाप":"measurement","कपड़ा":"garment","बिजली":"electrical","इलेक्ट्रिक":"electrical","सौर":"solar","मोबाइल":"mobile","मरम्मत":"repair","कृषि":"agriculture","खेती":"farm","कंप्यूटर":"computer","खाना":"food","खाद्य":"food","ब्यूटी":"beauty","सुंदरता":"beauty","हुनर":"skills","तकनीकी":"technical"}

def haversine(a,b,c,d):
    r=6371; p1,p2=math.radians(a),math.radians(c); dp=math.radians(c-a); dl=math.radians(d-b)
    h=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*r*math.asin(math.sqrt(h))

def recommend(profile,pathways,centres,demand):
    terms=set();skill_terms=set();interest_terms=set()
    for key in ("interests","skills","family_occupation","current_occupation"):
        val=profile.get(key,[])
        vals=val if isinstance(val,list) else [val]
        for v in vals:
            raw=str(v).lower().replace("-"," ").split();words=set(raw);words.update(ALIASES[w] for w in raw if w in ALIASES);terms.update(words)
            if key=="skills":skill_terms.update(words)
            else:interest_terms.update(words)
    district=str(profile.get("district","" )).lower();district={"नागपुर":"nagpur","पुणे":"pune"}.get(district,district)
    travel=profile.get("max_travel_distance")
    pref=profile.get("employment_preference")
    results=[]
    for p in pathways:
        required={str(x).lower() for x in (p.skills or [])}
        shared=terms & required
        interest_shared=interest_terms & required
        interest_match=1.0 if any(x in interest_terms for x in p.sector.lower().split()) else min(1.0,len(interest_shared)/3)
        skill_shared=skill_terms & required
        skill_match=min(1.0,len(skill_shared)/max(1,len(required)))
        # Demand is only a synthetic sample in this prototype; all sectors are neutral.
        relevance="Strong signals" if len(interest_shared)+len(skill_shared)>=2 else "Some signals" if interest_shared or skill_shared else "Explore this option"
        nearest=None
        local_centres=[c for c in centres if p.id in (c.pathway_ids or []) and (not district or c.district.lower()==district)]
        if local_centres: nearest=local_centres[0]
        elif any(p.id in (c.pathway_ids or []) for c in centres): nearest=next(c for c in centres if p.id in (c.pathway_ids or []))
        dist=None
        if nearest and profile.get("latitude") is not None and profile.get("longitude") is not None:
            dist=round(haversine(profile["latitude"],profile["longitude"],nearest.latitude,nearest.longitude),1)
        within=dist is None or travel is None or dist<=float(travel)
        # A known travel-limit violation is a hard constraint and removes the option.
        if not within: continue
        demand_row=next((d for d in demand if d.sector.lower()==p.sector.lower() and (not district or d.district.lower()==district)),None)
        demand_label=demand_row.demand_label if demand_row else "No district sample"
        demand_component=.5 if demand_row else 0.0
        feasible="Centre found" if nearest else "Centre not listed"
        if not within:feasible="Travel limit may be exceeded"
        pref_match="Fits stated preference" if not pref or pref=="either" or (pref=="self_employment" and p.self_employment) or (pref=="wage_employment" and not p.self_employment) else "Preference may differ"
        pref_component=1.0 if pref_match=="Fits stated preference" else .25
        already=[s for s in p.skills if s.lower() in skill_terms]; missing=[s for s in p.skills if s not in already]
        # Eligibility is unknown when catalogue prerequisites aren't verified; never fabricate a pass.
        eligibility="Needs counsellor verification" if p.min_education=="verify" or p.prerequisites else "Check with centre"
        explanation={"relevance":relevance,"matched_terms":sorted(shared),"demand":demand_label,"feasibility":feasible,"preference":pref_match,"eligibility":eligibility}
        # Stable deterministic ordering using only profile/pathway text relevance.
        feasibility_component=1.0 if within and nearest else .25 if nearest else 0.0
        weighted=WEIGHTS["interest"]*interest_match+WEIGHTS["skills"]*skill_match+WEIGHTS["demand"]*demand_component+WEIGHTS["feasibility"]*feasibility_component+WEIGHTS["preference"]*pref_component
        # Ordering uses a transparent deterministic weighted rule, while hiding arbitrary-looking score percentages.
        explanation["signals"]={"interest":"strong" if interest_match>.65 else "some" if interest_match else "limited","skills":"some overlap" if shared else "skills to build","local_demand":"synthetic neutral sample" if demand_row else "not available","feasibility":feasible}
        rank=(round(weighted,6),len(shared),p.title)
        results.append((rank,{"pathway":p,"explanation":explanation,"already_has":already,"to_develop":missing,"centre":nearest,"distance_km":dist,"demand":demand_label,"eligibility":eligibility,"within_travel_limit":within}))
    results.sort(key=lambda x:x[0],reverse=True)
    return [x[1] for x in results[:3]]
