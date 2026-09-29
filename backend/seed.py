"""Idempotent seed: simulated demo pathways/centres/demand, never beneficiary outcomes."""
from app.db import Base,engine,SessionLocal
from app.models import Pathway,TrainingCentre,DemandSignal
Base.metadata.create_all(bind=engine)
db=SessionLocal()
pathways=[
("demo-tailoring","Tailoring and garment enterprise skills","Apparel","garment work;tailoring;stitching;measurement;self employment",True),
("demo-food","Food processing and safe packaging","Food Processing","food;packaging;hygiene;small business",True),
("demo-electrical","Basic electrical maintenance","Electrical","electrical;wiring;repair;technical work",False),
("demo-solar","Solar installation foundations","Renewable Energy","solar;electrical;installation;maintenance",False),
("demo-mobile","Mobile phone repair foundations","Electronics","mobile;repair;electronics;technical work",True),
("demo-beauty","Beauty and wellness services","Beauty & Wellness","beauty;wellness;customer service;self employment",True),
("demo-handicraft","Handicraft product skills","Handicrafts","craft;handmade;design;self employment",True),
("demo-handloom","Handloom and weaving skills","Handloom","weaving;textile;loom;garment work",True),
("demo-welding","Welding foundations","Construction","welding;metal;fabrication;technical work",False),
("demo-plumbing","Plumbing foundations","Construction","plumbing;pipe;repair;technical work",True),
("demo-agri","Agriculture allied enterprise","Agriculture","agriculture;farm;dairy;animal care;enterprise",True),
("demo-digital","Digital service assistance","Digital Services","computer;digital forms;typing;customer service",True),
("demo-retail","Retail sales associate skills","Retail","retail;sales;customer service;stock",False),
("demo-two-wheeler","Two-wheeler service foundations","Automotive","two wheeler;repair;mechanic;technical work",True),
]
for pid,title,sector,skills,selfemp in pathways:
    if not db.get(Pathway,pid):
        db.add(Pathway(id=pid,title=title,sector=sector,description=f"Simulated demo pathway concept for {sector.lower()} interests. Not an official qualification.",skills=[x.strip() for x in skills.split(';')],prerequisites=[],min_education="verify",duration_hours=None,self_employment=selfemp,source="SIMULATED DEMO PATHWAY — not an active verified QP",source_url="",active=True))
db.flush()
ids=[x[0] for x in pathways]
centres=[
("demo-centre-1","Sample Skill Centre — demo","Nagpur","Demo block",21.1458,79.0882,"SIMULATED SAMPLE"),
("demo-centre-2","Sample Rural Training Hub — demo","Nagpur","Demo rural block",21.2058,79.1882,"SIMULATED SAMPLE"),
("demo-centre-3","Sample Livelihood Learning Point — demo","Pune","Demo block",18.5204,73.8567,"SIMULATED SAMPLE"),
]
for cid,name,district,block,lat,lon,source in centres:
    if not db.get(TrainingCentre,cid):
        offered=ids[:]
        db.add(TrainingCentre(id=cid,name=name,district=district,block=block,latitude=lat,longitude=lon,address="Sample location only — replace before operational use",contact="NOT VERIFIED",accessibility="NOT VERIFIED",source=source,pathway_ids=offered))
for district in ["Nagpur","Pune"]:
    for _,_,sector,_,_ in pathways:
        exists=db.query(DemandSignal).filter_by(district=district,sector=sector).first()
        if not exists:db.add(DemandSignal(district=district,sector=sector,demand_label="Sample signal",source="SIMULATED — not measured local demand",year=2026,capacity=0))
db.commit();db.close()
print("Seeded demo pathways, centres, and explicitly synthetic demand only.")
