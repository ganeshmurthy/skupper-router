#ifndef __tcp_lite_h__
#define __tcp_lite_h__ 1
/*
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */

#include "dispatch_private.h"
#include "delivery.h"
#include "adaptors/adaptor_common.h"
#include "adaptors/adaptor_listener.h"
#include "adaptors/adaptor_tls.h"
#include <qpid/dispatch/protocol_observer.h>


typedef struct tcplite_common_t     tcplite_common_t;
typedef struct tcplite_listener_t   tcplite_listener_t;
typedef struct tcplite_connector_t  tcplite_connector_t;
typedef struct tcplite_connection_t tcplite_connection_t;

ALLOC_DECLARE(tcplite_listener_t);
ALLOC_DECLARE(tcplite_connector_t);
ALLOC_DECLARE_SAFE(tcplite_connection_t);

DEQ_DECLARE(tcplite_listener_t,   tcplite_listener_list_t);
DEQ_DECLARE(tcplite_connector_t,  tcplite_connector_list_t);
DEQ_DECLARE(tcplite_connection_t, tcplite_connection_list_t);


typedef enum {
    TL_LISTENER,
    TL_CONNECTOR,
    TL_CONNECTION
} tcplite_context_type_t;

struct tcplite_common_t {
    tcplite_context_type_t  context_type;
    tcplite_common_t       *parent;
    vflow_record_t         *vflow;
};

struct tcplite_listener_t {
    tcplite_common_t           common;
    DEQ_LINKS(tcplite_listener_t);
    sys_mutex_t                lock;
    qd_adaptor_config_t       *adaptor_config;
    qd_tls_domain_t           *tls_domain;
    qd_adaptor_listener_t     *adaptor_listener;
    tcplite_connection_list_t  connections;
    qdpo_config_t             *protocol_observer_config;
    qdpo_t                    *protocol_observer;
    uint64_t                   connections_opened;
    uint64_t                   connections_closed;
    bool                       closing;
};


typedef struct tcplite_connector_t {
    tcplite_common_t           common;
    DEQ_LINKS(tcplite_connector_t);
    sys_mutex_t                lock;
    qd_timer_t                *activate_timer;
    qd_adaptor_config_t       *adaptor_config;
    qd_tls_domain_t           *tls_domain;
    qdr_connection_t          *core_conn;  // dispatcher conn and link
    uint64_t                   conn_id;
    uint64_t                   link_id;
    qdr_link_t                *out_link;
    tcplite_connection_list_t  connections;
    uint64_t                   connections_opened;
    uint64_t                   connections_closed;
    bool                       closing;
} tcplite_connector_t;


// LISTENER SIDE state machine:
//
typedef enum {
    LSIDE_INITIAL,       // Listener side raw connection accepted
    LSIDE_TLS_HANDSHAKE, // raw conn opened, TLS handshake in progress
    LSIDE_LINK_SETUP,    // raw conn/TLS opened, QDR connection and in/out QDR links attaching
    LSIDE_STREAM_START,  // reply-to set, inbound delivery and streaming msg initialized, wait for out stream/delivery
    LSIDE_FLOW,          // in/out deliveries and msg active; doing cleartext I/O
    LSIDE_TLS_FLOW,      // in/out deliveries and msg active; doing TLS I/O

    CSIDE_INITIAL,       // raw connection initiated, out delivery/msg available
    CSIDE_LINK_SETUP,    // raw conn/TLS opened, QDR conn and links attaching, waiting for inbound credit from core
    CSIDE_FLOW,          // in/out deliveries and msg active; doing I/O
    CSIDE_TLS_FLOW,      // in/out deliveries and msg active; doing TLS I/O
    XSIDE_CLOSING        // raw conn closing
} tcplite_connection_state_t;
ENUM_DECLARE(tcplite_connection_state);


//
// Important note about the polarity of the link/stream/delivery/disposition tuples:
//
//                   Listener Side      Connector Side
//               +------------------+-------------------+
//      Inbound  |      Client      |      Server       |
//               +------------------+-------------------+
//     Outbound  |      Server      |      Client       |
//               +------------------+-------------------+
//
typedef struct tcplite_connection_t {
    tcplite_common_t            common;
    DEQ_LINKS(tcplite_connection_t);
    pn_raw_connection_t        *raw_conn;
    sys_mutex_t                 activation_lock;
    sys_atomic_t                core_activation;
    sys_atomic_t                raw_opened;
    qd_timer_t                 *close_timer;
    qdr_connection_t           *core_conn;
    uint64_t                    conn_id;
    qdr_link_t                 *inbound_link;
    qd_message_t               *inbound_stream;
    qdr_delivery_t             *inbound_delivery;
    uint64_t                    inbound_disposition;
    uint64_t                    inbound_link_id;
    qdr_link_t                 *outbound_link;
    qd_message_t               *outbound_stream;
    qdr_delivery_t             *outbound_delivery;
    uint64_t                    outbound_disposition;
    uint64_t                    outbound_link_id;
    uint64_t                    inbound_octets;
    uint64_t                    outbound_octets;
    qd_buffer_t                *outbound_body;
    pn_condition_t             *error;
    char                       *reply_to;
    qd_tls_domain_t            *tls_domain;    // if configured, owned by this connection
    qd_tls_t                   *tls;           // tls session if configured
    char                       *alpn_protocol; // negotiated by TLS else 0
    qd_handler_context_t        context;
    tcplite_connection_state_t  state;
    qdpo_transport_handle_t    *observer_handle;
    struct {
        uint64_t                last_update;  // ingress: last byte count value received in PN_RECEIVED
        uint64_t                pending_ack;  // egress: bytes sent since last PN_RECEIVED generated
        uint64_t                closed_count; // ingress: total count of window closures
        bool                    disabled;     // window flow control disabled, no backpressure allowed
    } window;
    bool                        listener_side;
    bool                        inbound_credit;
    bool                        inbound_first_octet;
    bool                        outbound_first_octet;
    bool                        outbound_body_complete;
} tcplite_connection_t;


tcplite_listener_t *qd_dispatch_configure_tcp_listener_lite(qd_dispatch_t *qd, qd_entity_t *entity);
void                qd_dispatch_delete_tcp_listener_lite(qd_dispatch_t *qd, tcplite_listener_t *li);
qd_error_t          qd_entity_refresh_tcpListener_lite(qd_entity_t* entity, tcplite_listener_t *LSIDE_LINK_SETUP);

tcplite_connector_t *qd_dispatch_configure_tcp_connector_lite(qd_dispatch_t *qd, qd_entity_t *entity);
void                 qd_dispatch_delete_tcp_connector_lite(qd_dispatch_t *qd, tcplite_connector_t *co);
qd_error_t           qd_entity_refresh_tcpConnector_lite(qd_entity_t* entity, tcplite_connector_t *co);

#endif