// Reglas de negocio que la spec cita por id. La spec dice QUÉ se cumple; aquí está el CÓMO.
// Cada regla recibe la operación ("alta" | "edicion" | "baja"), el registro previo, el nuevo
// y todos los registros de la entidad. Devuelve null si se cumple, o {mensaje, campo?} si no.

const adminActivo = u => !!u && u.rol === "admin" && !!u.activo;

export const RULES = {
  ultimoAdminActivo({ op, prev, next, all }) {
    if (!adminActivo(prev)) return null;
    const otros = all.filter(u => u.id !== prev.id && adminActivo(u)).length;
    if (otros > 0) return null;
    if (op === "baja") return { mensaje: "No puedes dar de baja al único admin activo. Nombra otro admin primero." };
    if (op === "edicion" && !adminActivo(next))
      return { campo: next.rol !== "admin" ? "rol" : "activo", mensaje: "Es el único admin activo. Nombra otro admin antes de cambiarlo." };
    return null;
  }
};
