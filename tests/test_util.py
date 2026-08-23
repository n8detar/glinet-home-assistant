from custom_components.glinet_router.util import build_endpoint, router_unique_id


def test_build_endpoint_accepts_host_or_url() -> None:
    assert build_endpoint("192.168.8.1", use_ssl=False) == "http://192.168.8.1/rpc"
    assert build_endpoint("router.local/", use_ssl=True) == "https://router.local/rpc"
    assert (
        build_endpoint("http://router.local/rpc", use_ssl=True)
        == "http://router.local/rpc"
    )


def test_router_unique_id_hashes_private_identifiers() -> None:
    info = {"mac": "AA:BB:CC:DD:EE:FF", "serial": "private-serial"}
    unique_id = router_unique_id(info, "router.local")

    assert len(unique_id) == 20
    assert "AA" not in unique_id
    assert "private" not in unique_id
    assert unique_id == router_unique_id(info, "different-host")
