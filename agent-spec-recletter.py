def destination_authorized(state, action):
    letter = identify_letter(action.attachment)
    applicant = lookup_letter_owner(letter)

    reqs = request_service.query(applicant)

    return any(
        req.active
        and req.channel == "email"
        and action.to in req.allowed_destinations
        for req in reqs
    )