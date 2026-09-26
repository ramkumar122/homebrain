from homebrain.config import Auth401Style, Env, load_settings


def test_local_defaults():
    s = load_settings({})
    assert s.env is Env.LOCAL
    assert s.is_local
    assert s.auth_401_style is Auth401Style.SPEC
    assert s.mcp_resource_uri == "http://localhost:8080/mcp"
    assert s.dynamodb_endpoint_url is None


def test_aws_defaults_to_alexa_401_style():
    s = load_settings({"HB_ENV": "aws", "HB_PUBLIC_BASE_URL": "https://hb.example.com/"})
    assert s.auth_401_style is Auth401Style.ALEXA
    assert s.mcp_resource_uri == "https://hb.example.com/mcp"


def test_explicit_401_style_wins():
    assert (
        load_settings({"HB_ENV": "aws", "AUTH_401_STYLE": "spec"}).auth_401_style
        is Auth401Style.SPEC
    )
