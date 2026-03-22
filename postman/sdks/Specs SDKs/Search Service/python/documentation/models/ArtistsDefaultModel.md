# ArtistsDefaultModel

**Properties**

| Name                     | Type                              | Required | Description |
| :----------------------- | :-------------------------------- | :------- | :---------- |
| score                    | float                             | ✅       |             |
| enabled                  | int                               | ✅       |             |
| available_worldwide      | int                               | ✅       |             |
| artist_id                | int                               | ✅       |             |
| artist_name              | str                               | ✅       |             |
| update_date              | str                               | ❌       |             |
| latest_publish_date      | str                               | ❌       |             |
| downloads                | int                               | ❌       |             |
| genre                    | List[[GenreModel](GenreModel.md)] | ❌       |             |
| artist_image_uri         | str                               | ❌       |             |
| artist_image_dynamic_uri | str                               | ❌       |             |
