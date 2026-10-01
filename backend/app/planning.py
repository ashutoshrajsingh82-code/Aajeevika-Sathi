"""Shared deterministic workflow helpers used by both API and controlled agents."""

def action_plan(recommendation):
    if not recommendation:return []
    return [
        "Discuss this demo pathway with a counsellor.",
        "Confirm current course, entry requirements, fees and dates with the centre.",
        "Ask whether prior skills can be assessed before training.",
        "Agree on a training and livelihood plan that fits your time and travel needs.",
        "Create a follow-up check-in with your counsellor.",
    ]
