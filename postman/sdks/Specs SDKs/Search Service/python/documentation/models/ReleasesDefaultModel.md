# ReleasesDefaultModel

**Properties**

| Name                      | Type                                                            | Required | Description |
| :------------------------ | :-------------------------------------------------------------- | :------- | :---------- |
| score                     | float                                                           | ✅       |             |
| label                     | [TrackOrReleaseLabelModel](TrackOrReleaseLabelModel.md)         | ✅       |             |
| aggregator                | [ReleaseAggregatorModel](ReleaseAggregatorModel.md)             | ✅       |             |
| available_worldwide       | int                                                             | ✅       |             |
| exclusive                 | int                                                             | ✅       |             |
| publish_date              | str                                                             | ✅       |             |
| release_date              | str                                                             | ✅       |             |
| release_id                | int                                                             | ✅       |             |
| release_name              | str                                                             | ✅       |             |
| release_type              | str                                                             | ✅       |             |
| status                    | int                                                             | ✅       |             |
| update_date               | str                                                             | ✅       |             |
| current_status            | List[[CurrentStatusModel](CurrentStatusModel.md)]               | ❌       |             |
| genre                     | ReleasesDefaultModelGenre                                       | ❌       |             |
| tracks                    | List[[ReleaseTrackModel](ReleaseTrackModel.md)]                 | ❌       |             |
| key                       | List[[ReleaseKeyModel](ReleaseKeyModel.md)]                     | ❌       |             |
| artists                   | List[[TrackOrReleaseArtistModel](TrackOrReleaseArtistModel.md)] | ❌       |             |
| catalog_number            | str                                                             | ❌       |             |
| create_date               | str                                                             | ❌       |             |
| encoded_date              | str                                                             | ❌       |             |
| exclusive_date            | str                                                             | ❌       |             |
| streaming_date            | str                                                             | ❌       |             |
| preorder_date             | str                                                             | ❌       |             |
| label_manager             | str                                                             | ❌       |             |
| pre_order_date            | str                                                             | ❌       |             |
| upc                       | str                                                             | ❌       |             |
| price                     | [PriceModel](PriceModel.md)                                     | ❌       |             |
| is_explicit               | bool                                                            | ❌       |             |
| track_count               | int                                                             | ❌       |             |
| release_image_uri         | str                                                             | ❌       |             |
| release_image_dynamic_uri | str                                                             | ❌       |             |
| downloads                 | int                                                             | ❌       |             |
| is_hype                   | bool                                                            | ❌       |             |
| is_pre_order              | bool                                                            | ❌       |             |
| plays                     | int                                                             | ❌       |             |

# ReleasesDefaultModelGenre
