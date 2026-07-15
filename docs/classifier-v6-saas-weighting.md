# Classifier v6 SaaS weighting candidate

Baseline: `319a3d675bb339ccdd8bf516e8f59a3ea9fadaa9`

This candidate changes only SaaS-versus-content weighting:

- strong homepage SaaS business identity plus a product or commercial route family can outweigh a large content library;
- diverse SaaS route families remain a second structural path;
- Nomadic Matt- and WPBeginner-shaped publisher controls must remain content publishers;
- Basecamp-, Linear-, Intercom-, and Shopify-shaped controls must remain SaaS;
- classifier marker becomes `archetype_classifier_v6_saas_business_identity`;
- candidate fingerprint becomes `fa1bfae405d970fa`.

The final PR diff contains direct source and regression-test changes only; the one-shot patch scripts and temporary CI changes were removed after the first green validation run.

Focused production acceptance remains required for Signal, Buffer, Webflow, Nomadic Matt, WPBeginner, Basecamp, Linear, Intercom, and Shopify before release freeze.
