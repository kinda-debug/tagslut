# ChartsDefaultModel

**Properties**

| Name                    | Type                              | Required | Description |
| :---------------------- | :-------------------------------- | :------- | :---------- |
| score                   | float                             | ✅       |             |
| chart_id                | int                               | ✅       |             |
| chart_name              | str                               | ✅       |             |
| create_date             | str                               | ✅       |             |
| is_approved             | int                               | ✅       |             |
| update_date             | str                               | ✅       |             |
| enabled                 | int                               | ✅       |             |
| is_indexed              | int                               | ✅       |             |
| is_published            | int                               | ✅       |             |
| artist_id               | int                               | ❌       |             |
| artist_name             | str                               | ❌       |             |
| person_id               | int                               | ❌       |             |
| publish_date            | str                               | ❌       |             |
| item_type_id            | int                               | ❌       |             |
| person_username         | str                               | ❌       |             |
| track_count             | int                               | ❌       |             |
| chart_image_uri         | str                               | ❌       |             |
| chart_image_dynamic_uri | str                               | ❌       |             |
| genres                  | List[[GenreModel](GenreModel.md)] | ❌       |             |
