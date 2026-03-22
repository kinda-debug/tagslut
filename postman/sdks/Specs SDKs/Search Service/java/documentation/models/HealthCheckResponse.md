# HealthCheckResponse

Response model for the `health-check` endpoint.

**Properties**

| Name               | Type    | Required | Description                                                              |
| :----------------- | :------ | :------- | :----------------------------------------------------------------------- |
| remoteAddr         | String  | ✅       | The origin of the request.                                               |
| commitHash         | String  | ✅       | The current docker image used by the service.                            |
| serviceEsConnected | Boolean | ✅       | Bool that indicates if the service is connected to elasticsearch or not. |
