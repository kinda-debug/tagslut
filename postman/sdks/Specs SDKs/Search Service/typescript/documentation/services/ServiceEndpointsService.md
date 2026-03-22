# ServiceEndpointsService

A list of all methods in the `ServiceEndpointsService` service. Click on the method name to view detailed information about that method.

| Methods                                                             | Description                                                                   |
| :------------------------------------------------------------------ | :---------------------------------------------------------------------------- |
| [healthCheckSearchHealthCheckGet](#healthchecksearchhealthcheckget) | Endpoint used for health checking the service and the ES connectivity status. |

## healthCheckSearchHealthCheckGet

Endpoint used for health checking the service and the ES connectivity status.

- HTTP Method: `GET`
- Endpoint: `/search/health-check`

**Return Type**

`HealthCheckResponse`

**Example Usage Code Snippet**

```typescript
import { SearchServiceSdk } from 'search-service-sdk';

(async () => {
  const searchServiceSdk = new SearchServiceSdk({});

  const data = await searchServiceSdk.serviceEndpoints.healthCheckSearchHealthCheckGet();

  console.log(data);
})();
```
