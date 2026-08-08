"""One9Founders Cloud — OpenWorker-compatible sign-in + OAuth broker.

Data stays on One9Founders. Point OpenWorker's config.toml at this service:

    cloud_base_url = "https://api.one9founders.com"   # or http://127.0.0.1:8000
    cloud_auth_domain = "api.one9founders.com"        # host that serves /authorize
    cloud_client_id = "<COWORKER_CLOUD_CLIENT_ID>"
    cloud_audience = "https://api.one9founders.com"
"""
