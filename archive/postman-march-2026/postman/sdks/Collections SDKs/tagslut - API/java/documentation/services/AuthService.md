# AuthService

A list of all methods in the `AuthService` service. Click on the method name to view detailed information about that method.

| Methods                                                 | Description |
| :------------------------------------------------------ | :---------- |
| [getTokenClientCredentials](#gettokenclientcredentials) |             |
| [introspectToken](#introspecttoken)                     |             |

## getTokenClientCredentials

- HTTP Method: `POST`
- Endpoint: `/v4/auth/o/token`

**Parameters**

| Name                             | Type                                                                              | Required | Description  |
| :------------------------------- | :-------------------------------------------------------------------------------- | :------- | :----------- |
| getTokenClientCredentialsRequest | [GetTokenClientCredentialsRequest](../models/GetTokenClientCredentialsRequest.md) | ✅       | Request Body |

**Return Type**

`Object`

**Example Usage Code Snippet**

```java
import com.tagslutapisdk.TagslutApiSdk;
import com.tagslutapisdk.models.GetTokenClientCredentialsRequest;

public class Main {

  public static void main(String[] args) {
    TagslutApiSdk tagslutApiSdk = new TagslutApiSdk();

    GetTokenClientCredentialsRequest getTokenClientCredentialsRequest =
      GetTokenClientCredentialsRequest.builder()
        .grantType("client_credentials")
        .clientId("{{beatport_client_id}}")
        .clientSecret("{{beatport_client_secret}}")
        .build();

    Object response = tagslutApiSdk.auth.getTokenClientCredentials(
      getTokenClientCredentialsRequest
    );

    System.out.println(response);
  }
}

```

## introspectToken

- HTTP Method: `GET`
- Endpoint: `/v4/auth/o/introspect`

**Return Type**

`Object`

**Example Usage Code Snippet**

```java
import com.tagslutapisdk.TagslutApiSdk;

public class Main {

  public static void main(String[] args) {
    TagslutApiSdk tagslutApiSdk = new TagslutApiSdk();

    Object response = tagslutApiSdk.auth.introspectToken();

    System.out.println(response);
  }
}

```
