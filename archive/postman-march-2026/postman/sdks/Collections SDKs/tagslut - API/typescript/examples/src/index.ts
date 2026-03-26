import { TagslutApiSdk } from 'tagslut-api-sdk';

(async () => {
  const tagslutApiSdk = new TagslutApiSdk({});

  const data = await tagslutApiSdk.auth.introspectToken();

  console.log(data);
})();
