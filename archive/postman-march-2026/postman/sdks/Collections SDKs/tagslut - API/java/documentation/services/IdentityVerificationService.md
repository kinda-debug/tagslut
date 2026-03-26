# IdentityVerificationService

A list of all methods in the `IdentityVerificationService` service. Click on the method name to view detailed information about that method.

| Methods                                                | Description |
| :----------------------------------------------------- | :---------- |
| [\_5aBeatportIsrcLookup](#_5abeatportisrclookup)       |             |
| [\_5bTidalIsrcCrossCheck](#_5btidalisrccrosscheck)     |             |
| [\_5cSpotifyIsrcCrossCheck](#_5cspotifyisrccrosscheck) |             |

## \_5aBeatportIsrcLookup

- HTTP Method: `GET`
- Endpoint: `/v4/catalog/tracks`

**Parameters**

| Name              | Type                                                                             | Required | Description               |
| :---------------- | :------------------------------------------------------------------------------- | :------- | :------------------------ |
| requestParameters | [\_5aBeatportIsrcLookupParameters](../models/_5aBeatportIsrcLookupParameters.md) | ❌       | Request Parameters Object |

**Return Type**

`Object`

**Example Usage Code Snippet**

```java
import com.tagslutapisdk.TagslutApiSdk;
import com.tagslutapisdk.models.TracksByIsrcQueryParamParameters;

public class Main {

  public static void main(String[] args) {
    TagslutApiSdk tagslutApiSdk = new TagslutApiSdk();

    TracksByIsrcQueryParamParameters requestParameters = TracksByIsrcQueryParamParameters.builder()
      .isrc("{{beatport_test_isrc}}")
      .build();

    Object response = tagslutApiSdk.catalog.tracksByIsrcQueryParam(requestParameters);

    System.out.println(response);
  }
}

```

## \_5bTidalIsrcCrossCheck

- HTTP Method: `GET`
- Endpoint: `/v1/tracks`

**Parameters**

| Name              | Type                                                                               | Required | Description               |
| :---------------- | :--------------------------------------------------------------------------------- | :------- | :------------------------ |
| requestParameters | [\_5bTidalIsrcCrossCheckParameters](../models/_5bTidalIsrcCrossCheckParameters.md) | ❌       | Request Parameters Object |

**Return Type**

`Object`

**Example Usage Code Snippet**

```java
import com.tagslutapisdk.TagslutApiSdk;
import com.tagslutapisdk.models._5bTidalIsrcCrossCheckParameters;

public class Main {

  public static void main(String[] args) {
    TagslutApiSdk tagslutApiSdk = new TagslutApiSdk();

    _5bTidalIsrcCrossCheckParameters requestParameters = _5bTidalIsrcCrossCheckParameters
      .builder()
      .isrc("{{beatport_verified_isrc}}")
      .countryCode("US")
      .build();

    Object response = tagslutApiSdk.identityVerification._5bTidalIsrcCrossCheck(requestParameters);

    System.out.println(response);
  }
}

```

## \_5cSpotifyIsrcCrossCheck

- HTTP Method: `GET`
- Endpoint: `/v1/search`

**Parameters**

| Name              | Type                                                                                   | Required | Description               |
| :---------------- | :------------------------------------------------------------------------------------- | :------- | :------------------------ |
| requestParameters | [\_5cSpotifyIsrcCrossCheckParameters](../models/_5cSpotifyIsrcCrossCheckParameters.md) | ❌       | Request Parameters Object |

**Return Type**

`Object`

**Example Usage Code Snippet**

```java
import com.tagslutapisdk.TagslutApiSdk;
import com.tagslutapisdk.models._5cSpotifyIsrcCrossCheckParameters;

public class Main {

  public static void main(String[] args) {
    TagslutApiSdk tagslutApiSdk = new TagslutApiSdk();

    _5cSpotifyIsrcCrossCheckParameters requestParameters = _5cSpotifyIsrcCrossCheckParameters
      .builder()
      .q("isrc:{{beatport_verified_isrc}}")
      .type("track")
      .build();

    Object response = tagslutApiSdk.identityVerification._5cSpotifyIsrcCrossCheck(
      requestParameters
    );

    System.out.println(response);
  }
}

```
