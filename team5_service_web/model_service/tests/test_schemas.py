import pytest
from pydantic import ValidationError

from app.schemas import Features, PredictRequest


def valid_feature_kwargs():
    return dict(
        gender="Male",
        age=67,
        hypertension=0,
        heart_disease=1,
        ever_married="Yes",
        work_type="Private",
        residence_type="Urban",
        avg_glucose_level=228.69,
        bmi=36.6,
        smoking_status="formerly smoked",
    )


def test_features_accepts_valid_payload():
    features = Features(**valid_feature_kwargs())
    assert features.gender == "Male"


def test_features_allows_null_bmi():
    kwargs = valid_feature_kwargs()
    kwargs["bmi"] = None
    features = Features(**kwargs)
    assert features.bmi is None


@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("gender", "Unknown"),
        ("age", -5),
        ("age", 200),
        ("work_type", "Freelancer"),
        ("ever_married", "Maybe"),
        ("residence_type", "Suburban"),
        ("smoking_status", "vapes"),
        ("avg_glucose_level", -1),
        ("bmi", -10),
    ],
)
def test_features_rejects_invalid_values(field, bad_value):
    kwargs = valid_feature_kwargs()
    kwargs[field] = bad_value
    with pytest.raises(ValidationError):
        Features(**kwargs)


def test_predict_request_requires_source():
    with pytest.raises(ValidationError):
        PredictRequest(features=[Features(**valid_feature_kwargs())])


def test_predict_request_accepts_batch():
    request = PredictRequest(
        features=[Features(**valid_feature_kwargs()), Features(**valid_feature_kwargs())],
        source="scheduled",
    )
    assert len(request.features) == 2
