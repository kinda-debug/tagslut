import { Environment } from './http/environment';
import { SdkConfig } from './http/types';
import { AuthService } from './services/auth';
import { CatalogService } from './services/catalog';
import { SearchService } from './services/search';
import { MyLibraryService } from './services/my-library';
import { IdentityVerificationService } from './services/identity-verification';
import { ValidationRunService } from './services/validation-run';

export * from './services/auth';
export * from './services/catalog';
export * from './services/search';
export * from './services/my-library';
export * from './services/identity-verification';
export * from './services/validation-run';

export * from './http';
export { Environment } from './http/environment';

export class TagslutApiSdk {
  public readonly auth: AuthService;

  public readonly catalog: CatalogService;

  public readonly search: SearchService;

  public readonly myLibrary: MyLibraryService;

  public readonly identityVerification: IdentityVerificationService;

  public readonly validationRun: ValidationRunService;

  constructor(public config: SdkConfig) {
    this.auth = new AuthService(this.config);

    this.catalog = new CatalogService(this.config);

    this.search = new SearchService(this.config);

    this.myLibrary = new MyLibraryService(this.config);

    this.identityVerification = new IdentityVerificationService(this.config);

    this.validationRun = new ValidationRunService(this.config);
  }

  set baseUrl(baseUrl: string) {
    this.auth.baseUrl = baseUrl;
    this.catalog.baseUrl = baseUrl;
    this.search.baseUrl = baseUrl;
    this.myLibrary.baseUrl = baseUrl;
    this.identityVerification.baseUrl = baseUrl;
    this.validationRun.baseUrl = baseUrl;
  }

  set environment(environment: Environment) {
    this.auth.baseUrl = environment;
    this.catalog.baseUrl = environment;
    this.search.baseUrl = environment;
    this.myLibrary.baseUrl = environment;
    this.identityVerification.baseUrl = environment;
    this.validationRun.baseUrl = environment;
  }

  set timeoutMs(timeoutMs: number) {
    this.auth.timeoutMs = timeoutMs;
    this.catalog.timeoutMs = timeoutMs;
    this.search.timeoutMs = timeoutMs;
    this.myLibrary.timeoutMs = timeoutMs;
    this.identityVerification.timeoutMs = timeoutMs;
    this.validationRun.timeoutMs = timeoutMs;
  }

  set username(username: string) {
    this.auth.username = username;
    this.catalog.username = username;
    this.search.username = username;
    this.myLibrary.username = username;
    this.identityVerification.username = username;
    this.validationRun.username = username;
  }

  set password(password: string) {
    this.auth.password = password;
    this.catalog.password = password;
    this.search.password = password;
    this.myLibrary.password = password;
    this.identityVerification.password = password;
    this.validationRun.password = password;
  }

  set token(token: string) {
    this.auth.token = token;
    this.catalog.token = token;
    this.search.token = token;
    this.myLibrary.token = token;
    this.identityVerification.token = token;
    this.validationRun.token = token;
  }
}

// c029837e0e474b76bc487506e8799df5e3335891efe4fb02bda7a1441840310c
