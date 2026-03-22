# MyLibraryService

A list of all methods in the `MyLibraryService` service. Click on the method name to view detailed information about that method.

| Methods                               | Description |
| :------------------------------------ | :---------- |
| [myBeatportTracks](#mybeatporttracks) |             |
| [myAccount](#myaccount)               |             |

## myBeatportTracks

- HTTP Method: `GET`
- Endpoint: `/v4/my/beatport/tracks`

**Parameters**

| Name              | Type                                                                  | Required | Description               |
| :---------------- | :-------------------------------------------------------------------- | :------- | :------------------------ |
| requestParameters | [MyBeatportTracksParameters](../models/MyBeatportTracksParameters.md) | ❌       | Request Parameters Object |

**Return Type**

`Object`

**Example Usage Code Snippet**

```java
import com.tagslutapisdk.TagslutApiSdk;
import com.tagslutapisdk.models.MyBeatportTracksParameters;

public class Main {

  public static void main(String[] args) {
    TagslutApiSdk tagslutApiSdk = new TagslutApiSdk();

    MyBeatportTracksParameters requestParameters = MyBeatportTracksParameters.builder()
      .page("1")
      .perPage("25")
      .build();

    Object response = tagslutApiSdk.myLibrary.myBeatportTracks(requestParameters);

    System.out.println(response);
  }
}

```

## myAccount

- HTTP Method: `GET`
- Endpoint: `/v4/my/account`

**Return Type**

`Object`

**Example Usage Code Snippet**

```java
import com.tagslutapisdk.TagslutApiSdk;

public class Main {

  public static void main(String[] args) {
    TagslutApiSdk tagslutApiSdk = new TagslutApiSdk();

    Object response = tagslutApiSdk.myLibrary.myAccount();

    System.out.println(response);
  }
}

```
