"""Retired v1 training entry point.

The earlier script trained a synthetic model to infer clinical-style distress
scores from text and voice features. That is not a valid or safe basis for the
v2 non-diagnostic support-priority workflow, so the application no longer loads
or trains that model.
"""


def main():
    print(
        "Retired: this prototype does not train or use a distress-diagnosis model. "
        "Use the documented governance and validation process before adding any model."
    )


if __name__ == "__main__":
    main()
