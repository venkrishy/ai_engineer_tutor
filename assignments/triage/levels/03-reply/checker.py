def check(ticket, output):
    """Label, priority, and queue must match. The reply is checked against rules, not a canned text."""
    problems = []
    if output.get("id") != ticket["input"]["id"]:
        problems.append("id is missing or wrong")
    for field, value in ticket["expected"].items():
        if output.get(field) != value:
            problems.append(f"{field} does not match the rules")
    reply = output.get("reply")
    if not isinstance(reply, str) or not reply.strip():
        return problems + ["reply is missing"]
    if ticket["input"]["id"] not in reply:
        problems.append("reply does not contain the ticket id")
    if len(reply.split()) >= 80:
        problems.append("reply is 80 words or more")
    asks_for_refund = "refund" in (ticket["input"]["subject"] + " " + ticket["input"]["body"]).lower()
    if "refund" in reply.lower() and not asks_for_refund:
        problems.append("reply says refund but the ticket does not")
    return problems
