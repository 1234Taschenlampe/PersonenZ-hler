# Annotation Policy

Class list:

```text
0: person
```

Rules:

- Mark every actually visible person consistently.
- Put the bounding box around the visible body area.
- Do not invent invisible body parts.
- Mark partially visible people only when enough body evidence identifies a person.
- Do not label an isolated hand, single arm, or single leg without an identifiable person body.
- Do not label a hand directly in front of the lens as a person.
- Treat mirrors, screens, posters, photos, puppets and similar objects as negatives unless they must count as people in production.
- Mark small people in the relevant walking area.
- Give overlapping people separate boxes.
- Do not omit visible people.
- Empty images must have a valid empty label file.
- Labels must stay inside image bounds.
- Boxes must have non-zero width and height.
- Duplicate boxes are invalid.

Automated checks:

- Invalid classes
- Missing label files
- Boxes outside image bounds
- Extremely small boxes
- Duplicate boxes
- Corrupt images
- Class distribution
- Camera distribution
- Scenario distribution

Manual checks:

- Review a stratified sample from every camera, lighting condition and scenario before training.
