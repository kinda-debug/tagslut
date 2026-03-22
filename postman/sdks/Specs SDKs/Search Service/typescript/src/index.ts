import { Environment } from './http/environment';
import { SdkConfig } from './http/types';
import { ServiceEndpointsService } from './services/service-endpoints';
import { SearchEndpointsService } from './services/search-endpoints';

export * from './services/service-endpoints';
export * from './services/search-endpoints';

export * from './http';
export { Environment } from './http/environment';

export class SearchServiceSdk {
  public readonly serviceEndpoints: ServiceEndpointsService;

  public readonly searchEndpoints: SearchEndpointsService;

  constructor(public config: SdkConfig) {
    this.serviceEndpoints = new ServiceEndpointsService(this.config);

    this.searchEndpoints = new SearchEndpointsService(this.config);
  }

  set baseUrl(baseUrl: string) {
    this.serviceEndpoints.baseUrl = baseUrl;
    this.searchEndpoints.baseUrl = baseUrl;
  }

  set environment(environment: Environment) {
    this.serviceEndpoints.baseUrl = environment;
    this.searchEndpoints.baseUrl = environment;
  }

  set timeoutMs(timeoutMs: number) {
    this.serviceEndpoints.timeoutMs = timeoutMs;
    this.searchEndpoints.timeoutMs = timeoutMs;
  }

  set token(token: string) {
    this.serviceEndpoints.token = token;
    this.searchEndpoints.token = token;
  }
}

// c029837e0e474b76bc487506e8799df5e3335891efe4fb02bda7a1441840310c
