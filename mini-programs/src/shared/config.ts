// Build-time public configuration only. Never add secrets or shared access passwords.
export const config = {
  audience: 'customer' as 'customer' | 'clinic',
  apiBase: '',
  appid: 'touristappid',
  privacyReady: false,
};
