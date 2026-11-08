# User-supplied media

The default channel list and programme guide are empty. Add only streams you
are authorized to use. Each `channels` entry has `id`, `name`, and `sources`;
each source has a direct HTTP(S) `url`. Optional fields include `group`, `number`,
`tvgId`, `userAgent`, and `referer`. On the live-audio candidate branch, the
historical `player` (`kodi`) hint is ignored and live channels stay in the
internal player. Provider-specific resolver
protocols and station credentials are not included. No media URL is enabled.
For EPG updates set `enabled` to true and provide your own authorized HTTPS URL.
