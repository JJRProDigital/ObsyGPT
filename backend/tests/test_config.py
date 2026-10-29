from app.config import build_frontend_origins


def test_frontend_origins_include_localhost_pair_for_127_loopback():
    assert build_frontend_origins("http://127.0.0.1:5173") == [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ]


def test_frontend_origins_include_127_pair_for_localhost():
    assert build_frontend_origins("http://localhost:5173") == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


def test_frontend_origins_accept_comma_separated_values():
    assert build_frontend_origins("https://app.example.com, http://localhost:5173") == [
        "https://app.example.com",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
