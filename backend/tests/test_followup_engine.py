from datetime import date, timedelta
from types import SimpleNamespace
from app.followup import due_date_for,refresh_followup_state,followup_questions,outcome_view
import app.followup as followup

class FakeQuery:
    def __init__(self,rows):self.rows=rows
    def filter_by(self,**criteria):self.criteria=criteria;return self
    def all(self):return [r for r in self.rows if r.session_id==self.criteria["session_id"]]
class FakeDB:
    def __init__(self,rows=()):self.rows=list(rows);self.added=[]
    def query(self,_model):return FakeQuery(self.rows)
    def add(self,row):self.rows.append(row);self.added.append(row)
class FakeFollowUp:
    def __init__(self,**kwargs):self.__dict__.update(kwargs)
class FakeQuestionClient:
    def __init__(self,question_ids):self.question_ids=question_ids
    def generate_json(self,*args,**kwargs):return SimpleNamespace(question_ids=self.question_ids)

def test_configured_schedule_offsets_create_only_missing_intervals(monkeypatch):
    monkeypatch.setattr(followup,"FOLLOWUP_INTERVAL_DAYS",(7,30,90))
    db=FakeDB([SimpleNamespace(session_id="s1",schedule_offset_days=7,status="COMPLETED")])
    created=followup.schedule_default_followups(db,"s1","pathway",FakeFollowUp)
    assert [x.schedule_offset_days for x in created]==[30,90]
    assert all(x.status=="SCHEDULED" and x.due_date>date.today().isoformat() for x in created)
    assert due_date_for(7,today=date(2026,1,1))=="2026-01-08"

def test_due_and_missed_followups_are_derived_without_marking_completed_rows():
    due=SimpleNamespace(status="SCHEDULED",due_date=date.today().isoformat())
    missed=SimpleNamespace(status="SCHEDULED",due_date=(date.today()-timedelta(days=1)).isoformat())
    completed=SimpleNamespace(status="COMPLETED",due_date=(date.today()-timedelta(days=5)).isoformat())
    assert refresh_followup_state(due) and due.status=="DUE"
    assert refresh_followup_state(missed) and missed.status=="MISSED"
    assert not refresh_followup_state(completed) and completed.status=="COMPLETED"

def test_followup_questions_use_selected_pathway_and_verified_outcome_state():
    session=SimpleNamespace(state="FOLLOW_UP")
    case=SimpleNamespace(selected_pathway_id="path-1",_recommendations=[])
    result=followup_questions(session,case,None,"Electrical Basics")
    assert "Electrical Basics" in result["questions"][0]
    assert result["generated_by"]=="validated_case_state" and result["ai_used"] is False
    pathway=SimpleNamespace(category="TRAINING_STARTED",verification_status="VERIFIED")
    verified_questions=followup_questions(session,case,pathway,"Electrical Basics")
    assert verified_questions["questions"][0]=="Did you complete the recommended training?"
    verified=SimpleNamespace(id=1,session_id="s1",category="TRAINING_STARTED",source="beneficiary",reported_at=None,verification_status="UNVERIFIED",verification_note="",verified_by=None,verified_at=None,note="")
    unverified=followup_questions(session,case,verified,"Electrical Basics")
    assert "verify this update" in unverified["questions"][0]
    assert unverified["based_on"]["outcome_verified"] is False
    assert outcome_view(verified)["source"]=="beneficiary"

def test_ai_selects_only_preapproved_questions_and_invalid_selection_falls_back():
    session=SimpleNamespace(state="FOLLOW_UP",language="en");case=SimpleNamespace(selected_pathway_id="p1",_recommendations=[])
    selected=followup_questions(session,case,None,"Tailoring",FakeQuestionClient(["enrolment"]))
    assert selected["ai_used"] is True and selected["questions"]==["Were you able to enrol in Tailoring?"]
    invalid=followup_questions(session,case,None,"Tailoring",FakeQuestionClient(["work_status"]))
    assert invalid["ai_used"] is False and invalid["questions"]==["Were you able to enrol in Tailoring?","If not, what prevented enrolment?","What support would help you take the next step?"]
