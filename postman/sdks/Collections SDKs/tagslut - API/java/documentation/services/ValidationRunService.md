# ValidationRunService

A list of all methods in the `ValidationRunService` service. Click on the method name to view detailed information about that method.

| Methods                                                    | Description |
| :--------------------------------------------------------- | :---------- |
| [\_6aResolveTidalAlbumToIsrc](#_6aresolvetidalalbumtoisrc) |             |
| [\_6bTrackByIdValidation](#_6btrackbyidvalidation)         |             |
| [\_6cRunNotes](#_6crunnotes)                               |             |

## \_6aResolveTidalAlbumToIsrc

- HTTP Method: `GET`
- Endpoint: `/v1/albums/507881809/tracks`

**Parameters**

| Name              | Type                                                                                       | Required | Description               |
| :---------------- | :----------------------------------------------------------------------------------------- | :------- | :------------------------ |
| requestParameters | [\_6aResolveTidalAlbumToIsrcParameters](../models/_6aResolveTidalAlbumToIsrcParameters.md) | ❌       | Request Parameters Object |

**Return Type**

`Object`

**Example Usage Code Snippet**

```java
import com.tagslutapisdk.TagslutApiSdk;
import com.tagslutapisdk.models._6aResolveTidalAlbumToIsrcParameters;

public class Main {

  public static void main(String[] args) {
    TagslutApiSdk tagslutApiSdk = new TagslutApiSdk();

    _6aResolveTidalAlbumToIsrcParameters requestParameters = _6aResolveTidalAlbumToIsrcParameters
      .builder()
      .countryCode("US")
      .build();

    Object response = tagslutApiSdk.validationRun._6aResolveTidalAlbumToIsrc(requestParameters);

    System.out.println(response);
  }
}

```

## \_6bTrackByIdValidation

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

## \_6cRunNotes

- HTTP Method: `GET`
- Endpoint: `/`

**Return Type**

`Object`

**Example Usage Code Snippet**

```java
import com.tagslutapisdk.TagslutApiSdk;

public class Main {

  public static void main(String[] args) {
    TagslutApiSdk tagslutApiSdk = new TagslutApiSdk();

    Object response = tagslutApiSdk.validationRun._6cRunNotes();

    System.out.println(response);
  }
}

```
