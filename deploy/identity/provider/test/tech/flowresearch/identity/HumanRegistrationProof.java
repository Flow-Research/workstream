package tech.flowresearch.identity;

import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Proxy;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import org.keycloak.events.Event;
import org.keycloak.events.EventType;
import org.keycloak.events.admin.AdminEvent;
import org.keycloak.models.KeycloakSession;
import org.keycloak.models.KeycloakTransactionManager;
import org.keycloak.models.RealmModel;
import org.keycloak.models.RealmProvider;
import org.keycloak.models.UserModel;
import org.keycloak.models.UserProvider;

/** Checks failure/identity boundaries against the pinned provider interfaces. */
public final class HumanRegistrationProof {
    private static <T> T proxy(Class<T> type, InvocationHandler handler) {
        return type.cast(Proxy.newProxyInstance(type.getClassLoader(), new Class<?>[]{type}, handler));
    }

    public static void main(String[] args) {
        prove("flow", EventType.REGISTER, false, false, false, true);
        prove("other", EventType.REGISTER, false, false, false, false);
        prove("flow", EventType.LOGIN, false, false, false, false);
        prove("flow", EventType.REGISTER_ERROR, false, false, false, false);
        prove("flow", EventType.REGISTER, true, false, false, false);
        prove("flow", EventType.REGISTER, false, true, false, false);
        prove("flow", EventType.REGISTER, false, false, true, false);
        System.out.println("Flow registration listener boundary proof passed");
    }

    private static void prove(String realmName, EventType type, boolean lookupFails,
                              boolean writeFails, boolean serviceAccount, boolean writes) {
        AtomicBoolean rollback = new AtomicBoolean();
        AtomicReference<String> marker = new AtomicReference<>();
        RealmModel realm = proxy(RealmModel.class, (self, method, args) -> {
            if (method.getName().equals("getName")) return realmName;
            throw new AssertionError("Unexpected realm call");
        });
        UserModel user = proxy(UserModel.class, (self, method, args) -> {
            if (method.getName().equals("getServiceAccountClientLink")) return serviceAccount ? "machine" : null;
            if (method.getName().equals("setSingleAttribute")) {
                if (writeFails) throw new IllegalStateException("Injected write failure");
                if (!args[0].equals("workstream_subject_kind")) throw new AssertionError("Wrong attribute");
                marker.set((String) args[1]);
                return null;
            }
            throw new AssertionError("Unexpected user call");
        });
        RealmProvider realms = proxy(RealmProvider.class, (self, method, args) -> realm);
        UserProvider users = proxy(UserProvider.class, (self, method, args) -> {
            if (lookupFails) throw new IllegalStateException("Injected lookup failure");
            return user;
        });
        KeycloakTransactionManager transactions = proxy(KeycloakTransactionManager.class, (self, method, args) -> {
            if (!method.getName().equals("setRollbackOnly")) throw new AssertionError("Unexpected transaction call");
            rollback.set(true);
            return null;
        });
        KeycloakSession session = proxy(KeycloakSession.class, (self, method, args) -> switch (method.getName()) {
            case "realms" -> realms;
            case "users" -> users;
            case "getTransactionManager" -> transactions;
            default -> throw new AssertionError("Unexpected session call");
        });
        HumanRegistrationListener listener = new HumanRegistrationListener(session);
        Event event = new Event();
        event.setType(type);
        event.setRealmId("realm-id");
        event.setUserId("user-id");
        boolean failure = lookupFails || writeFails || serviceAccount;
        try {
            listener.onEvent(event);
            if (failure) throw new AssertionError("Expected failure");
        } catch (IllegalStateException expected) {
            if (!failure || !rollback.get()) throw new AssertionError("Failure did not require rollback");
        }
        if (writes ? !"human".equals(marker.get()) : marker.get() != null) throw new AssertionError("Wrong identity mutation");
        if (!failure && rollback.get()) throw new AssertionError("Unexpected rollback");
        marker.set(null);
        listener.onEvent((AdminEvent) null, false);
        if (marker.get() != null) throw new AssertionError("Administrative event assigned identity");
    }
}
