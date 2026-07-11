import asyncio

from dirigera_readaptive.client import HttpDirigeraClient


class FakeResponse:
    status_code = 202

    def __init__(self, payload=None):
        self._payload = payload or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class FakeSession:
    def __init__(self):
        self.patch_calls = []
        self.get_calls = []

    def patch(self, url, headers, json, timeout, verify):
        self.patch_calls.append(
            {
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": timeout,
                "verify": verify,
            }
        )
        return FakeResponse()

    def get(self, url, headers, timeout, verify):
        self.get_calls.append(
            {
                "url": url,
                "headers": headers,
                "timeout": timeout,
                "verify": verify,
            }
        )
        return FakeResponse({"id": "light-1"})

    def put(self, url, headers, json, timeout, verify):
        self.patch_calls.append(
            {
                "method": "PUT",
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": timeout,
                "verify": verify,
            }
        )
        return FakeResponse()


def test_activate_adaptive_uses_verified_top_level_patch_body():
    async def run():
        session = FakeSession()
        client = HttpDirigeraClient(host="192.0.2.10", token="token", session=session)

        await client.activate_adaptive("light-1", "profile-1")

        assert session.patch_calls == [
            {
                "url": "https://192.0.2.10:8443/v1/devices/light-1",
                "headers": {"Authorization": "Bearer token"},
                "json": [{"adaptiveProfile": {"id": "profile-1", "active": True}}],
                "timeout": 10,
                "verify": False,
            }
        ]

    asyncio.run(run())


def test_get_device_reads_device_endpoint():
    async def run():
        session = FakeSession()
        client = HttpDirigeraClient(host="192.0.2.10", token="token", session=session)

        device = await client.get_device("light-1")

        assert device == {"id": "light-1"}
        assert session.get_calls[0]["url"] == "https://192.0.2.10:8443/v1/devices/light-1"

    asyncio.run(run())


def test_update_adaptive_profile_uses_verified_put_route():
    async def run():
        session = FakeSession()
        client = HttpDirigeraClient(host="192.0.2.10", token="token", session=session)
        profile = {
            "id": "profile-1",
            "name": "Computed schedule",
            "adaptiveSchedule": [
                {"startTime": "20:00", "lightLevel": 81, "colorTemperature": 2000}
            ],
        }

        await client.update_adaptive_profile("profile-1", profile)

        assert session.patch_calls[-1] == {
            "method": "PUT",
            "url": "https://192.0.2.10:8443/v1/adaptive-profiles/profile-1",
            "headers": {"Authorization": "Bearer token"},
            "json": profile,
            "timeout": 10,
            "verify": False,
        }

    asyncio.run(run())
