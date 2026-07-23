import chromadb
import time
import os
from config import MEMORY_DIR, MEMORY_RESULTS_LIMIT


class Memory:
    """Memoria a largo plazo de MIA usando ChromaDB (base de datos vectorial).

    Almacena y recupera información semántica de forma persistente:
    - conversations: Diálogos pasados (pregunta + respuesta)
    - knowledge: Hechos, preferencias y datos aprendidos sobre Fernando

    Todo funciona 100% offline, persiste en disco.
    """

    def __init__(self):
        # Crear directorio de persistencia si no existe
        os.makedirs(MEMORY_DIR, exist_ok=True)

        print(f"🧬 Inicializando memoria vectorial en: {MEMORY_DIR}")

        # Cliente persistente (datos en disco)
        self._client = chromadb.PersistentClient(path=MEMORY_DIR)

        # Colecciones
        self._conversations = self._client.get_or_create_collection(
            name="conversations",
            metadata={"description": "Historial de conversaciones con Fernando"}
        )
        self._knowledge = self._client.get_or_create_collection(
            name="knowledge",
            metadata={"description": "Hechos y datos aprendidos"}
        )

        conv_count = self._conversations.count()
        know_count = self._knowledge.count()
        print(f"🧬 Memoria lista — {conv_count} conversaciones, {know_count} conocimientos almacenados")

    # ------------------------------------------------------------------
    # Conversaciones
    # ------------------------------------------------------------------

    def store_conversation(self, user_message, mia_response, visual_context=""):
        """Almacena un turno de conversación en la memoria a largo plazo.

        El documento combina la pregunta y respuesta para búsqueda semántica.
        Los metadatos permiten filtrar y reconstruir el diálogo.
        """
        timestamp = time.time()
        doc_id = f"conv_{int(timestamp * 1000)}"

        # Combinar pregunta + respuesta como documento buscable
        document = f"Cliente preguntó: {user_message}\nMIA respondió: {mia_response}"

        metadata = {
            "user_message": user_message[:500],     # Limitar tamaño de metadatos
            "mia_response": mia_response[:500],
            "visual_context": visual_context[:300] if visual_context else "",
            "timestamp": timestamp,
            "type": "conversation"
        }

        try:
            self._conversations.add(
                documents=[document],
                metadatas=[metadata],
                ids=[doc_id]
            )
        except Exception as e:
            print(f"⚠️ Error guardando conversación en memoria: {e}")

    def recall_conversations(self, query, n_results=None):
        """Busca conversaciones pasadas semánticamente similares al query.

        Retorna lista de dict con: user_message, mia_response, timestamp
        """
        if n_results is None:
            n_results = MEMORY_RESULTS_LIMIT

        if self._conversations.count() == 0:
            return []

        # No pedir más resultados de los que existen
        n_results = min(n_results, self._conversations.count())

        try:
            results = self._conversations.query(
                query_texts=[query],
                n_results=n_results
            )

            memories = []
            if results and results["metadatas"] and results["metadatas"][0]:
                for i, meta in enumerate(results["metadatas"][0]):
                    distance = results["distances"][0][i] if results.get("distances") else None
                    memories.append({
                        "user_message": meta.get("user_message", ""),
                        "mia_response": meta.get("mia_response", ""),
                        "visual_context": meta.get("visual_context", ""),
                        "timestamp": meta.get("timestamp", 0),
                        "relevance": 1 - (distance or 0)  # Convertir distancia a relevancia
                    })

            return memories

        except Exception as e:
            print(f"⚠️ Error buscando en memoria: {e}")
            return []

    # ------------------------------------------------------------------
    # Base de conocimiento
    # ------------------------------------------------------------------

    def store_knowledge(self, fact, category="general"):
        """Almacena un hecho o dato aprendido.

        Categorías sugeridas: 'preferencia', 'dato_personal', 'general', 'instruccion'
        """
        timestamp = time.time()
        doc_id = f"know_{int(timestamp * 1000)}"

        metadata = {
            "category": category,
            "timestamp": timestamp,
            "type": "knowledge"
        }

        try:
            self._knowledge.add(
                documents=[fact],
                metadatas=[metadata],
                ids=[doc_id]
            )
            print(f"🧬 Conocimiento almacenado [{category}]: {fact[:80]}...")
        except Exception as e:
            print(f"⚠️ Error guardando conocimiento: {e}")

    def recall_knowledge(self, query, n_results=None):
        """Busca hechos/conocimientos relevantes al query."""
        if n_results is None:
            n_results = MEMORY_RESULTS_LIMIT

        if self._knowledge.count() == 0:
            return []

        n_results = min(n_results, self._knowledge.count())

        try:
            results = self._knowledge.query(
                query_texts=[query],
                n_results=n_results
            )

            facts = []
            if results and results["documents"] and results["documents"][0]:
                for i, doc in enumerate(results["documents"][0]):
                    meta = results["metadatas"][0][i] if results["metadatas"] else {}
                    facts.append({
                        "fact": doc,
                        "category": meta.get("category", "general"),
                        "timestamp": meta.get("timestamp", 0)
                    })

            return facts

        except Exception as e:
            print(f"⚠️ Error buscando conocimiento: {e}")
            return []

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    def get_stats(self):
        """Retorna estadísticas de la memoria"""
        return {
            "conversations": self._conversations.count(),
            "knowledge": self._knowledge.count()
        }

    def format_memories_for_prompt(self, query):
        """Busca memorias relevantes y las formatea para incluir en un prompt LLM.

        Combina conversaciones pasadas + conocimiento en un texto conciso.
        """
        sections = []

        # Buscar conversaciones relevantes (limitado defensivamente)
        conversations = self.recall_conversations(query, n_results=MEMORY_RESULTS_LIMIT)
        if conversations:
            conv_lines = []
            for mem in conversations:
                # Filtrar negativas de memoria para evitar bucles de "no recuerdo"
                m_resp_lower = mem.get('mia_response', '').lower()
                bad_keywords = ["no tengo memoria", "no tengo recuerdos", "no guardo", "no poseo memoria", "como asistente", "asistente virtual", "problemas para conectarme"]
                if any(kw in m_resp_lower for kw in bad_keywords):
                    continue

                # Truncar los mensajes recuperados para evitar saturación de tokens (máx 512 en el S25)
                u_msg = mem['user_message'][:80]
                m_resp = mem['mia_response'][:120]
                conv_lines.append(
                    f"- Cliente dijo: \"{u_msg}\" "
                    f"→ Respondiste: \"{m_resp}\""
                )
            if conv_lines:
                sections.append(
                    "Recuerdos de conversaciones pasadas:\n" + "\n".join(conv_lines)
                )

        # Buscar conocimiento relevante
        knowledge = self.recall_knowledge(query, n_results=MEMORY_RESULTS_LIMIT)
        if knowledge:
            fact_lines = [f"- {k['fact'][:100]}" for k in knowledge]
            sections.append(
                "Datos que recuerdas:\n" + "\n".join(fact_lines)
            )

        return "\n\n".join(sections) if sections else ""
