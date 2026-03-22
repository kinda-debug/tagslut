# ServiceEndpointsService

A list of all methods in the `ServiceEndpointsService` service. Click on the method name to view detailed information about that method.

| Methods                                                                       | Description                                                                   |
| :---------------------------------------------------------------------------- | :---------------------------------------------------------------------------- |
| [health_check_search_health_check_get](#health_check_search_health_check_get) | Endpoint used for health checking the service and the ES connectivity status. |

## health_check_search_health_check_get

Endpoint used for health checking the service and the ES connectivity status.

- HTTP Method: `GET`
- Endpoint: `/search/health-check`

**Return Type**

`HealthCheckResponse`

**Example Usage Code Snippet**

```python
from search_service_sdk import SearchServiceSdk

sdk = SearchServiceSdk(
    access_token="YOUR_ACCESS_TOKEN",
    timeout=10000
)

result = sdk.service_endpoints.health_check_search_health_check_get()

print(result)
```
