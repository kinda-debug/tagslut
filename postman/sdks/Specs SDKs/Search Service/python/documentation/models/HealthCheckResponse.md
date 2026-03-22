# HealthCheckResponse

Response model for the `health-check` endpoint.

**Properties**

| Name                 | Type | Required | Description                                                              |
| :------------------- | :--- | :------- | :----------------------------------------------------------------------- |
| remote_addr          | str  | ✅       | The origin of the request.                                               |
| commit_hash          | str  | ✅       | The current docker image used by the service.                            |
| service_es_connected | bool | ✅       | Bool that indicates if the service is connected to elasticsearch or not. |
