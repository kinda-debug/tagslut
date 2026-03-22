from search_service_sdk import SearchServiceSdk

sdk = SearchServiceSdk(access_token="YOUR_ACCESS_TOKEN", timeout=10000)

result = sdk.service_endpoints.health_check_search_health_check_get()

print(result)
