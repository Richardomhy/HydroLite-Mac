# macOS Release Process

Create the isolated `hydrolite-build` environment, build the PyInstaller onedir backend and Swift shell, assemble and audit the bundle, then validate locally with ad-hoc signing. Public distribution requires an explicit Developer ID identity, verified ZIP/DMG, notarytool submission through a keychain profile, stapling, and a final Gatekeeper check.

Never commit build products, certificates, private keys, credentials, or update signing keys. Updates require HTTPS, Sparkle EdDSA, Apple signing, increasing versions, and matching bundle/team identity.
