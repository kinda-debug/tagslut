from tagslut_api_sdk import TagslutApiSdk, Environment

sdk = TagslutApiSdk(
    access_token="YOUR_ACCESS_TOKEN",
    username="YOUR_USERNAME",
    password="YOUR_PASSWORD",
    base_url=Environment.DEFAULT.value,
    timeout=10000,
)

result = sdk.auth.introspect_token()

print(result)
