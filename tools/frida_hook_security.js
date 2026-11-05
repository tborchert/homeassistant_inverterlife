// Frida hooks for the InverterLife/Tuya native security layer (libthing_security.so).
//
// These hook the Java wrappers at SecureNativeApi, so they log the exact inputs and outputs
// of the native crypto without disassembling the .so. Run the app, trigger login + a data
// refresh, and capture:
//   - computeDigest(signString, ?)  -> the request signature (confirms the sign algorithm/key)
//   - getEncryptoKey(requestId, ecode) / genKey(...) -> the real per-request AES key bytes
//   - encryptPostData / decryptResponseData -> plaintext <-> ciphertext pairs
//   - getChKey(ctx, appKey) -> the channel key the cloud wants on every request
//
// Usage (rooted device or emulator with frida-server running):
//   frida -U -f com.InverterLife -l tools/frida_hook_security.js
//
// This only READS values passing through the app. It sends nothing and changes nothing.

function hex(bytes) {
  if (bytes === null) return "null";
  var b = Java.array('byte', bytes), out = '';
  for (var i = 0; i < b.length; i++) out += ('0' + (b[i] & 0xff).toString(16)).slice(-2);
  return out;
}

Java.perform(function () {
  var S = Java.use('com.thingclips.smart.security.jni.SecureNativeApi');

  S.computeDigest.overload('java.lang.String', 'java.lang.String').implementation = function (a, b) {
    var r = this.computeDigest(a, b);
    console.log('\n[computeDigest] signString=\n' + a + '\n  arg2=' + b + '\n  => sign=' + r);
    return r;
  };

  S.getEncryptoKey.overload('java.lang.String', 'java.lang.String').implementation = function (reqId, ecode) {
    var r = this.getEncryptoKey(reqId, ecode);
    console.log('[getEncryptoKey] requestId=' + reqId + ' ecode=' + ecode + ' => key=' + hex(r));
    return r;
  };

  S.genKey.overload('java.lang.String', 'java.lang.String', 'java.lang.String').implementation = function (a, b, c) {
    var r = this.genKey(a, b, c);
    console.log('[genKey] a=' + a + ' b=' + b + ' c=' + c + ' => ' + r);
    return r;
  };

  S.getChKey.overload('android.content.Context', '[B').implementation = function (ctx, appKey) {
    var r = this.getChKey(ctx, appKey);
    console.log('[getChKey] appKey=' + Java.use('java.lang.String').$new(appKey) + ' => chKey=' + r);
    return r;
  };

  S.encryptPostData.overload('java.lang.String', '[B').implementation = function (reqId, plain) {
    var r = this.encryptPostData(reqId, plain);
    console.log('[encryptPostData] requestId=' + reqId
      + '\n  plaintext=' + Java.use('java.lang.String').$new(plain)
      + '\n  => cipher(hex)=' + hex(r));
    return r;
  };

  S.decryptResponseData.overload('java.lang.String', 'java.lang.String').implementation = function (a, b) {
    var r = this.decryptResponseData(a, b);
    console.log('[decryptResponseData] arg1=' + a + '\n  => plaintext=' + r);
    return r;
  };

  // Full parameter map, captured just before signing. Shows chKey, the exact key=value set,
  // the encrypted postData, time, requestId, etc. — i.e. the whole wire request.
  try {
    var Sign = Java.use('com.thingclips.sdk.network.ThingApiSignManager');
    Sign.generateSignatureSdk.overload('java.util.Map').implementation = function (map) {
      var out = '\n[request params]';
      var it = map.keySet().iterator();
      while (it.hasNext()) {
        var k = it.next();
        out += '\n  ' + k + ' = ' + map.get(k);
      }
      console.log(out);
      return this.generateSignatureSdk(map);
    };
  } catch (e) {
    console.log('[!] could not hook ThingApiSignManager: ' + e);
  }

  console.log('[*] SecureNativeApi hooks installed.');
});
