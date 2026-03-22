import { SearchServiceSdk } from 'search-service-sdk';

(async () => {
  const searchServiceSdk = new SearchServiceSdk({});

  const data = await searchServiceSdk.serviceEndpoints.healthCheckSearchHealthCheckGet();

  console.log(data);
})();
