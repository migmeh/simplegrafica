import { Routes } from '@angular/router';
import { DemoComponent } from './demo/demo.component';

export const routes: Routes = [

    // Ruta por defecto (opcional)
  { path: '', redirectTo: 'graficos', pathMatch: 'full' },

  // ⬅️ Nueva ruta para tu componente de gráficos
  {
    path: 'graficos', // La URL que usarás (ej. http://localhost:4200/graficos)
    component: DemoComponent // El componente que se cargará
  },
];
