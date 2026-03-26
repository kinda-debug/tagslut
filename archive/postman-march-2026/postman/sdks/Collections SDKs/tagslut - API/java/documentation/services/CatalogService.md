# CatalogService

A list of all methods in the `CatalogService` service. Click on the method name to view detailed information about that method.

| Methods                                                             | Description |
| :------------------------------------------------------------------ | :---------- |
| [trackById](#trackbyid)                                             |             |
| [tracksByIsrcQueryParam](#tracksbyisrcqueryparam)                   |             |
| [isrcStoreLookupPathBasedPhase3d](#isrcstorelookuppathbasedphase3d) |             |
| [releaseById](#releasebyid)                                         |             |
| [releaseTracks](#releasetracks)                                     |             |

## trackById

- HTTP Method: `GET`
- Endpoint: `/v4/catalog/tracks/{beatport_test_track_id}`

**Parameters**

| Name                | Type   | Required | Description |
| :------------------ | :----- | :------- | :---------- |
| beatportTestTrackId | String | ✅       |             |

**Return Type**

`Object`

**Example Usage Code Snippet**

```java
import com.tagslutapisdk.TagslutApiSdk;

public class Main {

  public static void main(String[] args) {
    TagslutApiSdk tagslutApiSdk = new TagslutApiSdk();

    Object response = tagslutApiSdk.catalog.trackById("beatport_test_track_id");

    System.out.println(response);
  }
}

```

## tracksByIsrcQueryParam

- HTTP Method: `GET`
- Endpoint: `/v4/catalog/tracks`

**Parameters**

| Name              | Type                                                                              | Required | Description               |
| :---------------- | :-------------------------------------------------------------------------------- | :------- | :------------------------ |
| requestParameters | [TracksByIsrcQueryParamParameters](../models/TracksByIsrcQueryParamParameters.md) | ❌       | Request Parameters Object |

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

## isrcStoreLookupPathBasedPhase3d

- HTTP Method: `GET`
- Endpoint: `/v4/catalog/tracks/store/{beatport_test_isrc}`

**Parameters**

| Name             | Type   | Required | Description |
| :--------------- | :----- | :------- | :---------- |
| beatportTestIsrc | String | ✅       |             |

**Return Type**

`Object`

**Example Usage Code Snippet**

```java
import com.tagslutapisdk.TagslutApiSdk;

public class Main {

  public static void main(String[] args) {
    TagslutApiSdk tagslutApiSdk = new TagslutApiSdk();

    Object response = tagslutApiSdk.catalog.isrcStoreLookupPathBasedPhase3d("beatport_test_isrc");

    System.out.println(response);
  }
}

```

## releaseById

- HTTP Method: `GET`
- Endpoint: `/v4/catalog/releases/{beatport_test_release_id}`

**Parameters**

| Name                  | Type   | Required | Description |
| :-------------------- | :----- | :------- | :---------- |
| beatportTestReleaseId | String | ✅       |             |

**Return Type**

`Object`

**Example Usage Code Snippet**

```java
import com.tagslutapisdk.TagslutApiSdk;

public class Main {

  public static void main(String[] args) {
    TagslutApiSdk tagslutApiSdk = new TagslutApiSdk();

    Object response = tagslutApiSdk.catalog.releaseById("beatport_test_release_id");

    System.out.println(response);
  }
}

```

## releaseTracks

- HTTP Method: `GET`
- Endpoint: `/v4/catalog/releases/{beatport_test_release_id}/tracks`

**Parameters**

| Name                  | Type                                                            | Required | Description               |
| :-------------------- | :-------------------------------------------------------------- | :------- | :------------------------ |
| beatportTestReleaseId | String                                                          | ✅       |                           |
| requestParameters     | [ReleaseTracksParameters](../models/ReleaseTracksParameters.md) | ❌       | Request Parameters Object |

**Return Type**

`Object`

**Example Usage Code Snippet**

```java
import com.tagslutapisdk.TagslutApiSdk;
import com.tagslutapisdk.models.ReleaseTracksParameters;

public class Main {

  public static void main(String[] args) {
    TagslutApiSdk tagslutApiSdk = new TagslutApiSdk();

    ReleaseTracksParameters requestParameters = ReleaseTracksParameters.builder()
      .perPage("100")
      .build();

    Object response = tagslutApiSdk.catalog.releaseTracks(
      "beatport_test_release_id",
      requestParameters
    );

    System.out.println(response);
  }
}

```
