// Local, Atoms-free replacement for `@metagptx/web-sdk`'s createClient().
//
// The app only used two pieces of the SDK:
//   - client.apiCall.invoke({ url, method, data, options })  -> axios-style call
//   - client.auth.login()                                    -> Atoms SSO trigger
//
// This shim reproduces both against our own backend using axios, so the app no
// longer depends on the MetaGPT/Atoms platform. Query params are expected to be
// baked into `url` by callers (matching the original SDK behavior); `data` is the
// JSON request body. The returned value is the raw axios response, so existing
// callers that read `response.data` keep working unchanged.
import axios, { AxiosRequestConfig, AxiosResponse } from 'axios';

import { getAPIBaseURL } from './config';

interface InvokeParams {
  url: string;
  method?: string;
  data?: Record<string, unknown> | undefined;
  options?: {
    headers?: Record<string, string>;
    timeout?: number;
    [key: string]: unknown;
  };
}

export function createClient() {
  return {
    apiCall: {
      async invoke(params: InvokeParams): Promise<AxiosResponse> {
        const { url, method = 'GET', data, options = {} } = params;

        // `__headers` is an internal marker some callers stuff into `data`;
        // strip it so it never reaches the request body.
        const body =
          data && typeof data === 'object'
            ? Object.fromEntries(
                Object.entries(data).filter(([k]) => k !== '__headers')
              )
            : data;

        const isGet = method.toUpperCase() === 'GET';

        const config: AxiosRequestConfig = {
          baseURL: getAPIBaseURL(),
          url,
          method: method as AxiosRequestConfig['method'],
          headers: options.headers ?? {},
          // GET requests carry their params in the URL string already.
          data: isGet ? undefined : body,
          timeout: options.timeout,
        };

        return axios(config);
      },
    },
    auth: {
      // Atoms single-sign-on is gone after de-coupling. The app's real login is
      // the custom-auth flow on /role-selection, so send users there. If you
      // later wire up your own OIDC provider, replace this with a redirect to
      // your backend's authorize endpoint.
      login(): void {
        window.location.replace('/role-selection');
      },
    },
  };
}
