# HealthCheckResponse

Response model for the `health-check` endpoint.

**Properties**

| Name               | Type    | Required | Description                                                              |
| :----------------- | :------ | :------- | :----------------------------------------------------------------------- |
| remoteAddr         | string  | ✅       | The origin of the request.                                               |
| commitHash         | string  | ✅       | The current docker image used by the service.                            |
| serviceEsConnected | boolean | ✅       | Bool that indicates if the service is connected to elasticsearch or not. |
