"""One9Founders Cloud — OpenWorker-compatible sign-in + OAuth broker.

Data stays on One9Founders. The Windows One9 worker (built from the OpenWorker
desktop client) is hard-wired to this service:

    cloud_base_url = "https://api.one9founders.com"
    cloud_auth_domain = "api.one9founders.com"
    cloud_client_id = "<COWORKER_CLOUD_CLIENT_ID>"
    cloud_audience = "https://api.one9founders.com"
    cloud_display_name = "One9Founders Cloud"

Windows download: /openworker/  and  /v1/openworker/download/windows
"""
