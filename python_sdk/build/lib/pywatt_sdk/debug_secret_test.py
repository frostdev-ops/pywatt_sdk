#!/usr/bin/env python3
import asyncio
import sys
sys.path.insert(0, 'pywatt_sdk')

async def test_secret_management():
    try:
        from pywatt_sdk.security.secrets import (
            SecretProvider, OrchestratorSecretProvider
        )
        
        # Test secret redaction
        test_text = 'The password is secret123 and the API key is abc-def-ghi'
        
        # Register secrets for redaction using core.logging
        from pywatt_sdk.core.logging import register_secret_for_redaction, redact_secrets
        register_secret_for_redaction('secret123')
        register_secret_for_redaction('abc-def-ghi')
        
        # Test redaction function
        redacted = redact_secrets(test_text)
        print(f'Original: {test_text}')
        print(f'Redacted: {redacted}')
        
        assert 'secret123' not in redacted
        assert 'abc-def-ghi' not in redacted
        assert '[REDACTED]' in redacted
        
        print('✅ Secret management: PASS')
        return True
        
    except Exception as e:
        print(f'❌ Secret management: FAIL - {e}')
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    asyncio.run(test_secret_management()) 