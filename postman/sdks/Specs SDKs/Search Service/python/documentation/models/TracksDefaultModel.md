# TracksDefaultModel

**Properties**

| Name                       | Type                                                            | Required | Description |
| :------------------------- | :-------------------------------------------------------------- | :------- | :---------- |
| score                      | float                                                           | ✅       |             |
| add_date                   | str                                                             | ✅       |             |
| artists                    | List[[TrackOrReleaseArtistModel](TrackOrReleaseArtistModel.md)] | ✅       |             |
| available_worldwide        | int                                                             | ✅       |             |
| change_date                | str                                                             | ✅       |             |
| current_status             | [CurrentStatusModel](CurrentStatusModel.md)                     | ✅       |             |
| enabled                    | int                                                             | ✅       |             |
| encode_status              | str                                                             | ✅       |             |
| exclusive_period           | int                                                             | ✅       |             |
| genre_enabled              | int                                                             | ✅       |             |
| is_available_for_streaming | int                                                             | ✅       |             |
| is_classic                 | int                                                             | ✅       |             |
| label                      | [TrackOrReleaseLabelModel](TrackOrReleaseLabelModel.md)         | ✅       |             |
| label_manager              | str                                                             | ✅       |             |
| mix_name                   | str                                                             | ✅       |             |
| publish_date               | str                                                             | ✅       |             |
| publish_status             | str                                                             | ✅       |             |
| release                    | [TrackReleaseModel](TrackReleaseModel.md)                       | ✅       |             |
| release_date               | str                                                             | ✅       |             |
| sale_type                  | str                                                             | ✅       |             |
| suggest                    | [TrackSuggestModel](TrackSuggestModel.md)                       | ✅       |             |
| supplier_id                | int                                                             | ✅       |             |
| track_id                   | int                                                             | ✅       |             |
| track_name                 | str                                                             | ✅       |             |
| track_number               | int                                                             | ✅       |             |
| update_date                | str                                                             | ✅       |             |
| was_ever_exclusive         | int                                                             | ✅       |             |
| bpm                        | int                                                             | ❌       |             |
| catalog_number             | str                                                             | ❌       |             |
| chord_type_id              | int                                                             | ❌       |             |
| exclusive_date             | str                                                             | ❌       |             |
| free_download_end_date     | str                                                             | ❌       |             |
| free_download_start_date   | str                                                             | ❌       |             |
| guid                       | str                                                             | ❌       |             |
| isrc                       | str                                                             | ❌       |             |
| key_id                     | int                                                             | ❌       |             |
| key_name                   | str                                                             | ❌       |             |
| length                     | int                                                             | ❌       |             |
| pre_order_date             | str                                                             | ❌       |             |
| streaming_date             | str                                                             | ❌       |             |
| downloads                  | int                                                             | ❌       |             |
| plays                      | int                                                             | ❌       |             |
| price                      | [PriceModel](PriceModel.md)                                     | ❌       |             |
| is_explicit                | bool                                                            | ❌       |             |
| is_available_for_alacarte  | bool                                                            | ❌       |             |
| is_dj_edit                 | bool                                                            | ❌       |             |
| is_ugc_remix               | bool                                                            | ❌       |             |
| is_pre_order               | bool                                                            | ❌       |             |
| track_image_uri            | str                                                             | ❌       |             |
| track_image_dynamic_uri    | str                                                             | ❌       |             |
| genre                      | TracksDefaultModelGenre                                         | ❌       |             |
| sub_genre                  | [SubGenreModel](SubGenreModel.md)                               | ❌       |             |

# TracksDefaultModelGenre
