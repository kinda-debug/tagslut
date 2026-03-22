import { z } from 'zod';
import { ThrowableError } from '../../../http/errors/throwable-error';
import {
  ValidationError,
  validationError,
  validationErrorRequest,
  validationErrorResponse,
} from './validation-error';

export type IHttpValidationErrorSchema = {
  detail?: ValidationError[];
};

export const httpValidationErrorResponse = z.lazy(() => {
  return z
    .object({
      detail: z.array(validationErrorResponse).optional(),
    })
    .transform((data) => ({
      detail: data['detail'],
    }));
});

export class HttpValidationError extends ThrowableError {
  public detail?: ValidationError[];
  constructor(
    public message: string,
    protected response?: unknown,
  ) {
    super(message);

    const parsedResponse = httpValidationErrorResponse.parse(response);

    this.detail = parsedResponse.detail;
  }

  public throw() {
    const error = new HttpValidationError(this.message, this.response);
    error.metadata = this.metadata;
    throw error;
  }
}
