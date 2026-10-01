"""Grounded AI-assisted recommendation explanations; scoring remains deterministic."""
import json
from ..schemas import RecommendationContext,RecommendationExplanationChoice

SYSTEM_PROMPT=("Choose only explanation codes supported by the supplied validated recommendation context. "
"Do not add facts, eligibility claims, course details, or government information. Return only the required JSON.")

class RecommendationExplanationService:
    def explain(self,context:dict,client=None,session_id:str|None=None):
        safe=RecommendationContext.model_validate(context)
        choice=None;ai_assisted=False
        if client is not None:
            prompt=("Select a primary reason, training focus, and next step based only on this validated data. "
                    "Use combined_alignment only when both interest and skill signals exist; use skill_alignment only when matched skills exist; "
                    "use interest_alignment only when a stated interest or nonzero semantic/deterministic interest match exists. "
                    "Choose build_missing_skills only when missing_skills is nonempty. Choose contact_listed_centre only when centre_found is true; "
                    "choose review_travel only when a distance is available. Data:\n"+
                    json.dumps(safe.model_dump(),ensure_ascii=False,separators=(",",":")))
            try:
                proposed=client.generate_json(prompt,RecommendationExplanationChoice,system=SYSTEM_PROMPT,operation="recommendation_explanation",session_id=session_id)
                self._validate_choice(safe,proposed)
                choice=proposed;ai_assisted=True
            except Exception:
                # Invalid or unavailable explanation generation cannot alter or block recommendation results.
                choice=None
        if choice is None:choice=self._fallback_choice(safe)
        return self._render(safe,choice,ai_assisted)

    @staticmethod
    def _validate_choice(context,choice):
        interest=bool(context.stated_interests) or context.interest_score>0 or context.semantic_interest_similarity>0
        skill=bool(context.matched_skills) or context.skills_score>0 or context.semantic_skill_similarity>0
        if choice.primary_reason=="interest_alignment" and not interest:raise ValueError("Unsupported interest claim")
        if choice.primary_reason=="skill_alignment" and not context.matched_skills:raise ValueError("Unsupported skill claim")
        if choice.primary_reason=="combined_alignment" and not (interest and context.matched_skills):raise ValueError("Unsupported combined claim")
        if choice.training_focus=="build_missing_skills" and not context.missing_skills:raise ValueError("No listed training gap")
        if choice.training_focus=="verify_requirements" and context.missing_skills:raise ValueError("Missing skills should be shown")
        if choice.next_step=="contact_listed_centre" and not context.centre_found:raise ValueError("No centre is listed")
        if choice.next_step=="review_travel" and context.approximate_distance_km is None:raise ValueError("No distance is available")

    @staticmethod
    def _fallback_choice(context):
        interest=bool(context.stated_interests) or context.interest_score>0 or context.semantic_interest_similarity>0
        skill=bool(context.matched_skills)
        reason="combined_alignment" if interest and skill else "interest_alignment" if interest else "skill_alignment" if skill else "exploration"
        next_step="contact_listed_centre" if context.centre_found else "review_travel" if context.approximate_distance_km is not None else "counsellor_review"
        return RecommendationExplanationChoice(primary_reason=reason,training_focus="build_missing_skills" if context.missing_skills else "verify_requirements",next_step=next_step)

    @staticmethod
    def _render(context,choice,ai_assisted):
        interest_names=", ".join(context.stated_interests[:4])
        reason={
            "interest_alignment":f"The catalogue description has a semantic or deterministic match to the interests you shared{': '+interest_names if interest_names else ''}.",
            "skill_alignment":f"Your recorded skills match listed pathway skills: {', '.join(context.matched_skills)}.",
            "combined_alignment":f"This option connects your stated interests{': '+interest_names if interest_names else ''} and recorded skills ({', '.join(context.matched_skills)}).",
            "exploration":"This is an option to explore; the available profile signals show no strong match.",
        }[choice.primary_reason]
        training=(f"Consider training to build these listed skills: {', '.join(context.missing_skills)}. Confirm the course content and entry requirements with the centre." if choice.training_focus=="build_missing_skills" else "The catalogue does not list specific skill gaps. Confirm course content and entry requirements with a counsellor or centre.")
        if choice.next_step=="review_travel":
            next_step=f"Review the approximate {context.approximate_distance_km:g} km travel distance with a counsellor before deciding."
        else:
            next_step={"counsellor_review":"Ask a counsellor to verify eligibility, training availability, cost, and next steps.","contact_listed_centre":"Contact the listed sample centre to verify current availability, schedule, fees, and entry requirements."}[choice.next_step]
        return {"why_pathway":reason,"matched_skills":context.matched_skills,"missing_skills":context.missing_skills,"training_needed":training,"next_steps":[next_step],"uncertainties":["Catalogue entries and local demand are demo data; eligibility and availability are unverified."],"generated_by":"ai_assisted_grounded_choice" if ai_assisted else "validated_deterministic_fallback","reason_code":choice.primary_reason}
