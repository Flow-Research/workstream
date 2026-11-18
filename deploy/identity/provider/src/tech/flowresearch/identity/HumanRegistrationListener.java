package tech.flowresearch.identity;

import org.keycloak.events.Event;
import org.keycloak.events.EventType;
import org.keycloak.events.EventListenerProvider;
import org.keycloak.events.admin.AdminEvent;
import org.keycloak.models.KeycloakSession;
import org.keycloak.models.RealmModel;
import org.keycloak.models.UserModel;

/** Assign human identity only to successful Flow self-registration, in its transaction. */
public final class HumanRegistrationListener implements EventListenerProvider {
    private final KeycloakSession session;

    public HumanRegistrationListener(KeycloakSession session) {
        this.session = session;
    }

    @Override
    public void onEvent(Event event) {
        if (event.getType() != EventType.REGISTER || event.getError() != null) {
            return;
        }
        RealmModel realm = session.realms().getRealm(event.getRealmId());
        if (realm == null || !"flow".equals(realm.getName())) {
            return;
        }
        UserModel user = session.users().getUserById(realm, event.getUserId());
        if (user == null || user.getServiceAccountClientLink() != null) {
            session.getTransactionManager().setRollbackOnly();
            throw new IllegalStateException("Flow registration requires a participant account");
        }
        user.setSingleAttribute("workstream_subject_kind", "human");
    }

    @Override
    public void onEvent(AdminEvent event, boolean includeRepresentation) {
        // Administrative provisioning must explicitly assign identity; it is not signup.
    }

    @Override
    public void close() {}
}
