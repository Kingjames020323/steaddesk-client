#include <jni.h>

JNIEXPORT jint JNICALL Java_com_carriez_flutter_1hbb_MerchantRecovery_sessionState(
        JNIEnv *env, jclass recovery) {
    jclass scenarios = (*env)->FindClass(env, "com/carriez/flutter_hbb/BinderScenarios");
    jfieldID session = (*env)->GetStaticFieldID(env, scenarios, "session", "I");
    return (*env)->GetStaticIntField(env, scenarios, session);
}
