"""Turn a casebook investigation into a cited analyst briefing using a local model."""
from local_llama import InferenceError, MODEL, structured_review

VERSION = "case-review-v1"
CHECKS = {
    "owner": "Ask the account owner whether they initiated the activity.",
    "provider": "Inspect the identity-provider sign-in and MFA records for the cited time.",
    "gateway": "Check whether these accounts used an approved shared gateway.",
    "travel": "Compare the sign-in with approved travel and device enrollment.",
    "shift": "Compare the UTC time with the user's approved shift and time zone.",
}
RULE_CHECKS = {"R1": ("provider", "owner"), "R2": ("gateway", "provider"),
               "R3": ("travel", "owner"), "R4": ("shift", "owner")}
RULE_GAPS = {"R1": "The cause of the failed attempts is unknown.",
             "R2": "The logs do not identify the people or gateway behind the shared source.",
             "R3": "Device enrollment and travel approval are unknown.",
             "R4": "The user's shift and time zone are unknown."}


def statements(finding):
    """Ground each statement in exactly one trigger and its own direct or historical evidence."""
    trigger, features = finding["trigger_id"], finding["features"]
    prior = finding["evidence"]["prior_account_successes"]
    recent = finding["evidence"]["source_failures_5m"]
    outcome = "successful" if features["success"] else "failed"
    facts = {}
    for hit in finding["rule_hits"]:
        rule = hit["rule"]
        refs = hit["event_ids"]
        if rule == "R1":
            text = (f"The {outcome} login followed {features['prior_pair_failures_5m']} failures "
                    "for this account and IP in the preceding five minutes.")
        elif rule == "R2":
            text = (f"This failure brought the number of distinct accounts with failed logins from this IP "
                    f"to {features['source_accounts_with_current_5m']} within five minutes.")
        elif rule == "R3":
            text = (f"The successful login used a device and country unseen in this account's "
                    f"{features['device_samples']} prior device observations and "
                    f"{features['country_samples']} prior country observations.")
            refs = [*prior, trigger]
        elif rule == "R4":
            text = (f"Of {features['prior_successes']} earlier successful logins for this account, "
                    f"{features['prior_hour_band_count']} fell in the UTC hour of this success "
                    "or either adjacent hour.")
            refs = [*prior, trigger]
        else:
            raise InferenceError(f"Unsupported rule in case: {rule}")
        facts[rule] = {"trigger_id": trigger, "signal": rule, "text": text, "event_ids": refs}
    model = finding["model"]
    relation = "met or exceeded" if model["alert"] else "was below"
    facts["forest"] = {"trigger_id": trigger, "signal": "forest",
                       "text": (f"The Isolation Forest score for this {outcome} login was "
                                f"{model['score']:.6f} and {relation} the {model['threshold']:.6f} threshold."),
                       "event_ids": list(dict.fromkeys([*prior, *recent, trigger]))}
    if not finding["rule_hits"]:
        inputs = model["inputs"]
        facts["forest"]["text"] += (
            f" The observed inputs included {inputs['prior_pair_failures_5m']} earlier account/IP "
            f"failures in five minutes and a smoothed personal hour share of "
            f"{inputs['personal_hour_share']:.4f}.")
    return facts


def review_leads(case):
    """Keep the earliest instance of each distinct pattern in the chronological case."""
    leads = {}
    seen = set()
    for finding in case["findings"]:
        facts = statements(finding)
        if any(ref not in case["sources"] for fact in facts.values() for ref in fact["event_ids"]):
            raise InferenceError("Case contains a reference outside its source records")
        candidates = finding["attack_candidates"]
        covered = {r for candidate in candidates for r in candidate["supporting_rules"]}
        paths = [(c["supporting_rules"], c) for c in candidates]
        paths.extend(([hit["rule"]], None) for hit in finding["rule_hits"] if hit["rule"] not in covered)
        if not paths:
            paths.append(([], None))
        for rules, candidate in paths:
            tid = candidate["technique_id"] if candidate else None
            signature = (tid, tuple(rules), finding["features"]["success"], finding["model"]["alert"])
            if signature in seen:
                continue
            seen.add(signature)
            trigger = finding["trigger_id"]
            if candidate:
                hypothesis = {"technique_id": tid, "name": case["attack_catalog"][tid]["name"],
                              "status": "candidate", "trigger_id": trigger, "basis": list(rules),
                              "reason": candidate["reason"], "alternative": candidate["alternative"]}
                gap = candidate["missing"]
            else:
                hypothesis = None
                gap = RULE_GAPS[rules[0]] if rules else (
                    "The score alone cannot establish who initiated the login or why it was unusual.")
            checks = list(dict.fromkeys(c for r in rules for c in RULE_CHECKS[r])) or ["owner", "provider"]
            leads[f"L{len(leads) + 1}"] = {"trigger_id": trigger, "facts": [facts[r] for r in [*rules, "forest"]],
                                           "hypothesis": hypothesis, "gap": gap, "checks": checks}
    if not leads:
        raise InferenceError("Case has no supported trigger to explain")
    return leads


def render(case, leads, selection):
    keys = {"primary", "context", "check"}
    if not isinstance(selection, dict) or set(selection) != keys or not all(
            isinstance(value, str) for value in selection.values()):
        raise InferenceError("Invalid case review structure")
    primary, context, check = (selection[k] for k in ("primary", "context", "check"))
    if primary not in leads or (context != "none" and (context not in leads or context == primary)):
        raise InferenceError("Unknown or repeated case reference")
    lead = leads[primary]
    if check not in lead["checks"]:
        raise InferenceError("Requested check is unsupported by the primary finding")
    chosen = [lead] if context == "none" else [lead, leads[context]]
    facts = {}
    for item in chosen:
        for fact in item["facts"]:
            facts[fact["trigger_id"], fact["signal"]] = fact
    return {"case_id": case["case_id"], "primary_trigger_id": lead["trigger_id"],
            "facts": list(facts.values()), "hypotheses": [v["hypothesis"] for v in chosen if v["hypothesis"]],
            "missing_information": [{"trigger_id": v["trigger_id"], "text": v["gap"]} for v in chosen],
            "recommended_checks": [{"trigger_id": lead["trigger_id"], "check": check, "text": CHECKS[check]}],
            "scope": {"case_triggers": case["trigger_count"], "available_leads": len(leads),
                      "selected_leads": len(chosen)}}


def explain_case(case, mode="llama", model=MODEL):
    leads = review_leads(case)
    if mode == "baseline":
        # Reproducible comparator: most supporting rules, then earliest insertion.
        primary = max(leads, key=lambda k: len(leads[k]["facts"]))
        selection = {"primary": primary, "context": "none", "check": leads[primary]["checks"][0]}
        return {"source": "template", "version": VERSION, "review": render(case, leads, selection)}
    if mode != "llama":
        raise ValueError("Unknown explanation mode")
    options = []
    for key, item in leads.items():
        hypothesis = item["hypothesis"]
        options.append({"id": key, "observations": [f["text"] for f in item["facts"]],
                        "candidate": hypothesis["technique_id"] if hypothesis else None,
                        "missing": item["gap"], "permitted_checks": item["checks"]})
    values = {"primary": list(leads), "context": ["none", *leads] if len(leads) > 1 else ["none"],
              "check": sorted({check for item in leads.values() for check in item["checks"]})}
    schema = {"type": "object", "additionalProperties": False, "required": list(values),
              "properties": {k: {"type": "string", "enum": v} for k, v in values.items()}}
    prompt = ("You are reviewing a synthetic authentication case for a SOC analyst. Choose one primary lead. "
              "Prefer a lead corroborated by multiple observations where available. Pick a check from that "
              "lead's permitted_checks to resolve its uncertainty. Use a different lead for context only if "
              "it adds evidence; otherwise use none. ATT&CK entries are hypotheses. Return only the requested JSON.")
    answer = structured_review(model, prompt, {"leads": options, "check_definitions": CHECKS}, schema,
                               lambda choice: render(case, leads, choice))
    return {"version": VERSION, **answer}
