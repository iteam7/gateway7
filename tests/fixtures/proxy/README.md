# Synthetic proxy TLS fixtures

These public certificates and the private key are only for local, offline tests.
They contain no real credentials and must never be trusted or deployed outside the tests.

`synthetic-ca.pem` signs `synthetic-server.pem`, whose names cover the three provider origins and loopback proxy.
`synthetic-server-key.pem` is an intentionally public test key.
The certificates are valid from 2020-01-01 to 2040-01-01.
They were generated for this fixture; the CA private key is not retained.

The tests load the CA into narrowly injected TLS contexts with certificate and hostname checks enabled.
They require no certificate generator, external network or extra dependency at runtime.
