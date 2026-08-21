from astromesh.runtime.confirmacion import Pendientes, es_confirmacion, huella


class TestEsConfirmacion:
    def test_las_formas_normales_de_decir_que_si(self):
        # "listo" no está en la lista `si, confirmo, dale, ok` de la spec,
        # pero es una forma tan común de asentir en rioplatense como las
        # otras cuatro — se decidió mantenerla (CONFIRMACIONES es
        # deliberadamente generosa, ver su comentario) y cubrirla acá en vez
        # de sacarla.
        for t in ["si", "SI", "Sí", " sí ", "confirmo", "CONFIRMO", "dale", "ok", "Ok", "listo"]:
            assert es_confirmacion(t) is True, t

    def test_lo_que_no_es_una_confirmacion(self):
        # "bueno dale pero cambiame la cantidad" es un mensaje NUEVO, no un sí:
        # interpretarlo sería exactamente lo que este gate existe para no hacer.
        for t in [
            "sip",
            "bueno dale pero cambiame la cantidad",
            "no",
            "sí pero no",
            "quiero dos",
            "",
            "   ",
            None,
        ]:
            assert es_confirmacion(t) is False, t


class TestHuella:
    def test_los_mismos_argumentos_dan_la_misma_huella_en_cualquier_orden(self):
        assert huella("praxis_crear_record", {"a": 1, "b": 2}) == huella(
            "praxis_crear_record", {"b": 2, "a": 1}
        )

    def test_argumentos_distintos_dan_huellas_distintas(self):
        # El bypass que esto cierra: confirmar dos unidades y ejecutar doscientas.
        assert huella("praxis_crear_record", {"cantidad": 2}) != huella(
            "praxis_crear_record", {"cantidad": 200}
        )

    def test_tools_distintas_dan_huellas_distintas(self):
        assert huella("praxis_crear_record", {}) != huella("praxis_actualizar_record", {})

    def test_un_argumento_no_serializable_no_rompe_la_huella(self):
        # `default=str` en `json.dumps` es lo que evita esto — sin el test,
        # es sólo una afirmación en un comentario.
        huella("t", {"x": object()})


class TestPendientes:
    def test_sin_pendiente_nada_esta_permitido(self):
        # Falla cerrado: es la propiedad que hace que perder el estado sea
        # molesto y no peligroso.
        p = Pendientes()
        assert p.permitido("s1", "t", "fp") is False

    def test_registrar_solo_no_alcanza(self):
        # Registrar es "quedó propuesto", no "quedó autorizado".
        p = Pendientes()
        p.registrar("s1", "praxis_crear_record", "fp1")
        assert p.permitido("s1", "praxis_crear_record", "fp1") is False

    def test_el_camino_feliz(self):
        p = Pendientes()
        p.registrar("s1", "praxis_crear_record", "fp1")
        assert p.habilitar("s1", "si") is True
        assert p.permitido("s1", "praxis_crear_record", "fp1") is True

    def test_habilitar_sin_pendiente_no_habilita_nada(self):
        p = Pendientes()
        assert p.habilitar("s1", "si") is False

    def test_confirmado_pero_con_otros_argumentos_no_pasa(self):
        p = Pendientes()
        p.registrar("s1", "praxis_crear_record", "fp1")
        p.habilitar("s1", "si")
        assert p.permitido("s1", "praxis_crear_record", "fp-otro") is False

    def test_confirmado_pero_otra_tool_no_pasa(self):
        p = Pendientes()
        p.registrar("s1", "praxis_crear_record", "fp1")
        p.habilitar("s1", "si")
        assert p.permitido("s1", "praxis_actualizar_record", "fp1") is False

    def test_un_mensaje_que_no_confirma_descarta_el_pendiente(self):
        # Vence en un turno: no queda un permiso flotando tres mensajes después,
        # cuando la conversación ya habla de otra cosa.
        p = Pendientes()
        p.registrar("s1", "praxis_crear_record", "fp1")
        assert p.habilitar("s1", "mejor mandame el catálogo") is False
        assert p.habilitar("s1", "si") is False
        assert p.permitido("s1", "praxis_crear_record", "fp1") is False

    def test_las_sesiones_no_se_cruzan(self):
        # Es TODO el aislamiento que hay entre dos conversaciones distintas.
        p = Pendientes()
        p.registrar("s1", "praxis_crear_record", "fp1")
        assert p.habilitar("s2", "si") is False
        assert p.permitido("s2", "praxis_crear_record", "fp1") is False

    def test_cerrar_consume_la_habilitacion(self):
        # Una confirmación vale para UNA corrida. Sin esto, un "si" habilitaría
        # la misma escritura en cada mensaje siguiente de la sesión.
        p = Pendientes()
        p.registrar("s1", "praxis_crear_record", "fp1")
        p.habilitar("s1", "si")
        p.cerrar("s1")
        assert p.permitido("s1", "praxis_crear_record", "fp1") is False

    def test_pendiente_devuelve_los_argumentos_registrados(self):
        # `pendiente()` es lo que el runtime usa para redactar, con sus
        # propias palabras, tanto el aviso de confirmación como el rechazo
        # que le muestra al modelo qué está esperando de verdad.
        p = Pendientes()
        p.registrar("s1", "praxis_crear_record", "fp1", {"cantidad": 2})
        assert p.pendiente("s1") == {
            "fp": "fp1",
            "tool": "praxis_crear_record",
            "ok": False,
            "argumentos": {"cantidad": 2},
        }

    def test_pendiente_sin_nada_devuelve_none(self):
        p = Pendientes()
        assert p.pendiente("s1") is None

    def test_pendiente_no_consume_ni_modifica_nada(self):
        # De sólo lectura: mirarlo no debe alterar si algo sigue permitido.
        p = Pendientes()
        p.registrar("s1", "praxis_crear_record", "fp1")
        p.habilitar("s1", "si")
        p.pendiente("s1")
        assert p.permitido("s1", "praxis_crear_record", "fp1") is True
