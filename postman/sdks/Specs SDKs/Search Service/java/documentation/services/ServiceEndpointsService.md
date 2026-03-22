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

```java
import com.searchservicesdk.SearchServiceSdk;
import com.searchservicesdk.models.HealthCheckResponse;

public class Main {

  public static void main(String[] args) {
    SearchServiceSdk searchServiceSdk = new SearchServiceSdk();

    HealthCheckResponse response =
      searchServiceSdk.serviceEndpoints.healthCheckSearchHealthCheckGet();

    System.out.println(response);
  }
}

```
